from django.contrib.auth import (
    authenticate,
    login,
    logout,
    password_validation,
    update_session_auth_hash,
)
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.decorators import method_decorator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.core.tenancy import clear_active_business, resolve_tenant, set_active_business
from apps.core.throttling import EmailScopedThrottle, ScopedThrottle

from . import services
from .models import User
from .serializers import (
    ChangePasswordSerializer,
    EmailSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    RegisterSerializer,
    SessionSerializer,
    TokenSerializer,
    UserSerializer,
)


def session_payload(request) -> dict:
    user = request.user
    if not user.is_authenticated:
        return {
            "authenticated": False,
            "user": None,
            "memberships": [],
            "portal_links": [],
            "active_workspace": None,
        }

    from apps.customers.models import CustomerPortalAccess

    memberships = [
        {"business_id": m.business.public_id, "business_name": m.business.name, "role": m.role}
        for m in user.memberships.select_related("business")
        .filter(is_active=True, business__is_active=True)
        .order_by("business__name")
    ]
    portal_links = [
        {
            "business_id": link.customer.business.public_id,
            "business_name": link.customer.business.name,
            "customer_id": link.customer.public_id,
            "customer_name": link.customer.display_name,
        }
        for link in CustomerPortalAccess.objects.select_related("customer__business")
        .filter(user=user, revoked_at__isnull=True, customer__business__is_active=True)
        .order_by("customer__business__name")
    ]
    tenant = resolve_tenant(request)
    active = None
    if tenant is not None:
        active = {
            "id": tenant.business.public_id,
            "name": tenant.business.name,
            "role": tenant.role,
            "timezone": tenant.business.timezone,
            "currency": tenant.business.currency,
        }
    return {
        "authenticated": True,
        "user": UserSerializer(user).data,
        "memberships": memberships,
        "portal_links": portal_links,
        "active_workspace": active,
    }


def _auto_select_workspace(request) -> None:
    """After login, select the only workspace a user has. With several, the user picks."""
    if resolve_tenant(request) is not None:
        return
    memberships = list(
        request.user.memberships.select_related("business").filter(
            is_active=True, business__is_active=True
        )[:2]
    )
    if len(memberships) == 1:
        set_active_business(request, memberships[0].business)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """Restores the client session: who is logged in and which workspace is active.

    Also sets the CSRF cookie the SPA needs for unsafe requests.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(responses=SessionSerializer)
    def get(self, request):
        return Response(session_payload(request))


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "register"

    @extend_schema(request=RegisterSerializer, responses={201: SessionSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(**serializer.validated_data)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(session_payload(request), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle, EmailScopedThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses=SessionSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            email=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            raise DomainError("Email or password is incorrect.", code="invalid_credentials")
        login(request, user)  # rotates the session key
        _auto_select_workspace(request)
        return Response(session_payload(request))


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        clear_active_business(request)
        logout(request)  # flushes the whole session
        return Response(status=status.HTTP_204_NO_CONTENT)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "public_token"

    @extend_schema(request=TokenSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.verify_email(serializer.validated_data["token"])
        if user is None:
            raise DomainError(
                "This verification link is invalid or has expired.", code="invalid_token"
            )
        return Response(UserSerializer(user).data)


class ResendVerificationView(APIView):
    throttle_classes = [ScopedThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=None, responses={202: None})
    def post(self, request):
        if not request.user.is_email_verified:
            services.send_verification_email(request.user)
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle, EmailScopedThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=EmailSerializer, responses={202: None})
    def post(self, request):
        serializer = EmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.send_password_reset(serializer.validated_data["email"])
        # Same answer whether or not the account exists.
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(
                pk=int(force_str(urlsafe_base64_decode(data["uid"]))), is_active=True
            )
        except (ValueError, TypeError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise DomainError(
                "This reset link is invalid or has already been used.", code="invalid_token"
            )
        try:
            password_validation.validate_password(data["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages}) from exc
        user.set_password(data["new_password"])
        # Proving control of the inbox also verifies the address.
        if user.email_verified_at is None:
            from django.utils import timezone

            user.email_verified_at = timezone.now()
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(request=UserSerializer, responses=UserSerializer)
    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    throttle_classes = [ScopedThrottle]
    throttle_scope = "sensitive"

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
