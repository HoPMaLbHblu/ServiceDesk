from drf_spectacular.utils import extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import SessionSerializer
from apps.accounts.views import session_payload
from apps.core.api import TenantViewMixin
from apps.core.exceptions import DomainError
from apps.core.tenancy import OWNER, STAFF, HasWorkspaceRole, require_tenant, set_active_business
from apps.core.throttling import ScopedThrottle

from . import services
from .models import Invitation, Membership
from .serializers import (
    BusinessSerializer,
    ChangeRoleSerializer,
    CreateBusinessSerializer,
    InvitationCreateSerializer,
    InvitationPreviewSerializer,
    InvitationSerializer,
    InvitationTokenSerializer,
    MemberSerializer,
    StaffOptionSerializer,
    SwitchWorkspaceSerializer,
    WorkspaceSerializer,
)


class WorkspaceListView(APIView):
    """Workspaces the user belongs to, and onboarding of a new business."""

    @extend_schema(responses=WorkspaceSerializer(many=True))
    def get(self, request):
        memberships = (
            Membership.objects.select_related("business")
            .filter(user=request.user, is_active=True, business__is_active=True)
            .order_by("business__name")
        )
        return Response(WorkspaceSerializer(memberships, many=True).data)

    @extend_schema(request=CreateBusinessSerializer, responses={201: SessionSerializer})
    def post(self, request):
        serializer = CreateBusinessSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        business = services.create_business(
            owner=request.user,
            name=data.pop("name"),
            timezone_name=data.pop("timezone"),
            currency=data.pop("currency"),
            tax_rate=data.pop("tax_rate"),
            **data,
        )
        set_active_business(request, business)
        return Response(session_payload(request), status=status.HTTP_201_CREATED)


class SwitchWorkspaceView(APIView):
    @extend_schema(request=SwitchWorkspaceSerializer, responses=SessionSerializer)
    def post(self, request):
        serializer = SwitchWorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = (
            Membership.objects.select_related("business")
            .filter(
                user=request.user,
                business__public_id=serializer.validated_data["business_id"],
                is_active=True,
                business__is_active=True,
            )
            .first()
        )
        if membership is None:
            # Same answer for "does not exist" and "not a member".
            raise DomainError("Workspace not found.", code="workspace_not_found")
        set_active_business(request, membership.business)
        return Response(session_payload(request))


class CurrentBusinessView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"get": STAFF, "patch": OWNER}

    @extend_schema(responses=BusinessSerializer)
    def get(self, request):
        return Response(BusinessSerializer(require_tenant(request).business).data)

    @extend_schema(request=BusinessSerializer, responses=BusinessSerializer)
    def patch(self, request):
        tenant = require_tenant(request)
        serializer = BusinessSerializer(tenant.business, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        business = services.update_settings(
            business=tenant.business, actor=request.user, data=serializer.validated_data
        )
        return Response(BusinessSerializer(business).data)


class MemberViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Membership.objects.select_related("user", "business").order_by(
        "-is_active", "user__full_name"
    )
    serializer_class = MemberSerializer
    role_rules = {"*": OWNER, "staff_options": STAFF}
    filterset_fields = ["role", "is_active"]
    search_fields = ["user__full_name", "user__email"]
    pagination_class = None

    @extend_schema(request=ChangeRoleSerializer, responses=MemberSerializer)
    @action(detail=True, methods=["post"])
    def change_role(self, request, pk=None):
        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.change_role(
            membership=self.get_object(),
            new_role=serializer.validated_data["role"],
            actor=request.user,
        )
        return Response(MemberSerializer(membership).data)

    @extend_schema(request=None, responses=MemberSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        membership = services.deactivate_member(membership=self.get_object(), actor=request.user)
        return Response(MemberSerializer(membership).data)

    @extend_schema(responses=StaffOptionSerializer(many=True))
    @action(detail=False, methods=["get"])
    def staff_options(self, request):
        """Active staff who can be assigned work (owners, managers and technicians)."""
        members = self.get_queryset().filter(is_active=True)
        return Response(StaffOptionSerializer(members, many=True).data)


class InvitationViewSet(TenantViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Invitation.objects.select_related("invited_by", "business").order_by("-created_at")
    serializer_class = InvitationSerializer
    role_rules = {"*": OWNER}
    lookup_field = "public_id"
    pagination_class = None

    @extend_schema(request=InvitationCreateSerializer, responses={201: InvitationSerializer})
    def create(self, request):
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation, _raw = services.invite_member(
            business=self.tenant.business, inviter=request.user, **serializer.validated_data
        )
        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=InvitationSerializer)
    @action(detail=True, methods=["post"])
    def revoke(self, request, public_id=None):
        invitation = services.revoke_invitation(invitation=self.get_object(), actor=request.user)
        return Response(InvitationSerializer(invitation).data)


class InvitationPreviewView(APIView):
    """Shows who invited whom before the recipient signs in. Reveals nothing without the token."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedThrottle]
    throttle_scope = "public_token"

    @extend_schema(request=InvitationTokenSerializer, responses=InvitationPreviewSerializer)
    def post(self, request):
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = services.find_invitation(serializer.validated_data["token"])
        if invitation is None:
            raise DomainError("This invitation is invalid.", code="invalid_invitation")
        return Response(
            {
                "business_name": invitation.business.name,
                "email": invitation.email,
                "role": invitation.role,
                "status": invitation.status,
            }
        )


class InvitationAcceptView(APIView):
    throttle_classes = [ScopedThrottle]
    throttle_scope = "public_token"

    @extend_schema(request=InvitationTokenSerializer, responses=SessionSerializer)
    def post(self, request):
        serializer = InvitationTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.accept_invitation(
            user=request.user, raw_token=serializer.validated_data["token"]
        )
        set_active_business(request, membership.business)
        return Response(session_payload(request))
