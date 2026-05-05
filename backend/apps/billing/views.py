import json
import logging

from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.exceptions import DomainError
from apps.core.tenancy import OWNER, STAFF, HasWorkspaceRole, require_tenant

from . import services
from .models import Plan
from .providers import DevBillingProvider, get_provider

logger = logging.getLogger(__name__)


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["code", "name", "price_monthly", "currency", "max_staff", "max_orders_per_month"]


class SubscriptionStateSerializer(serializers.Serializer):
    provider = serializers.CharField()
    provider_label = serializers.CharField()
    status = serializers.CharField()
    plan = PlanSerializer()
    trial_ends_at = serializers.DateTimeField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()
    past_due_since = serializers.DateTimeField(allow_null=True)
    can_write = serializers.BooleanField()
    read_only_reason = serializers.CharField()
    usage = serializers.DictField()
    plans = PlanSerializer(many=True)


class PlanChoiceSerializer(serializers.Serializer):
    plan = serializers.SlugRelatedField(
        slug_field="code", queryset=Plan.objects.filter(is_public=True)
    )


class RedirectSerializer(serializers.Serializer):
    url = serializers.URLField()


def _state(business) -> dict:
    from django.utils import timezone

    from apps.businesses.models import Membership
    from apps.orders.models import RepairOrder

    subscription = services.subscription_for(business)
    access = services.access_state(subscription)
    provider = (
        get_provider()
        if settings.BILLING_PROVIDER == "stripe" and settings.STRIPE_SECRET_KEY
        else DevBillingProvider()
    )
    month_start = (
        timezone.now()
        .astimezone(business.tzinfo)
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    return {
        "provider": subscription.provider if subscription else provider.name,
        "provider_label": provider.label,
        "status": subscription.status if subscription else "none",
        "plan": PlanSerializer(subscription.plan).data if subscription else None,
        "trial_ends_at": subscription.trial_ends_at if subscription else None,
        "current_period_end": subscription.current_period_end if subscription else None,
        "cancel_at_period_end": subscription.cancel_at_period_end if subscription else False,
        "past_due_since": subscription.past_due_since if subscription else None,
        "can_write": access.can_write,
        "read_only_reason": access.reason,
        "usage": {
            "staff": Membership.objects.filter(business=business, is_active=True).count(),
            "orders_this_month": RepairOrder.objects.filter(
                business=business, created_at__gte=month_start
            ).count(),
        },
        "plans": PlanSerializer(Plan.objects.filter(is_public=True), many=True).data,
    }


class SubscriptionView(APIView):
    """Billing endpoints stay usable when the workspace is read-only, so owners can fix billing."""

    permission_classes = [HasWorkspaceRole]
    role_rules = {"get": STAFF}

    @extend_schema(responses=SubscriptionStateSerializer)
    def get(self, request):
        return Response(_state(require_tenant(request).business))


class CheckoutView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"post": OWNER}

    @extend_schema(request=PlanChoiceSerializer, responses=RedirectSerializer)
    def post(self, request):
        tenant = require_tenant(request)
        serializer = PlanChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not request.user.is_email_verified:
            raise DomainError(
                "Verify your email address before changing the plan.", code="email_not_verified"
            )
        subscription = services.subscription_for(tenant.business)
        url = get_provider().checkout_url(
            subscription=subscription, plan=serializer.validated_data["plan"]
        )
        return Response({"url": url})


class PortalView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"post": OWNER}

    @extend_schema(request=None, responses=RedirectSerializer)
    def post(self, request):
        tenant = require_tenant(request)
        return Response(
            {
                "url": get_provider().portal_url(
                    subscription=services.subscription_for(tenant.business)
                )
            }
        )


class DevBillingActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["activate", "payment_failed", "payment_succeeded", "cancel"]
    )
    plan = serializers.SlugRelatedField(
        slug_field="code", queryset=Plan.objects.all(), required=False
    )


class DevBillingView(APIView):
    """Development billing mode only: simulate provider events through the real event pipeline."""

    permission_classes = [HasWorkspaceRole]
    role_rules = {"post": OWNER}

    @extend_schema(request=DevBillingActionSerializer, responses=SubscriptionStateSerializer)
    def post(self, request):
        if settings.BILLING_PROVIDER != "dev":
            raise DomainError("Development billing is disabled.", code="dev_billing_disabled")
        tenant = require_tenant(request)
        serializer = DevBillingActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscription = services.subscription_for(tenant.business)
        action = serializer.validated_data["action"]
        plan = serializer.validated_data.get("plan")
        event_type, status_value = {
            "activate": ("checkout.session.completed", None),
            "payment_failed": ("invoice.payment_failed", None),
            "payment_succeeded": ("invoice.paid", None),
            "cancel": ("customer.subscription.deleted", "canceled"),
        }[action]
        event = DevBillingProvider.synthetic_event(
            event_type=event_type, subscription=subscription, plan=plan, status=status_value
        )
        services.process_event(provider="dev", event=event)
        record(
            action="billing.dev_event",
            entity=tenant.business,
            business=tenant.business,
            actor=request.user,
            changes={"simulated": event_type},
        )
        return Response(_state(tenant.business))


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(APIView):
    """Signed Stripe webhooks. Unsigned or wrongly signed requests are rejected with 400."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request):
        if settings.BILLING_PROVIDER != "stripe":
            return HttpResponse(status=status.HTTP_404_NOT_FOUND)
        provider = get_provider()
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = provider.parse_webhook(request.body, signature)
        except Exception as exc:  # invalid signature or payload: reject without processing
            logger.warning("stripe_webhook_rejected", extra={"error": type(exc).__name__})
            return HttpResponse(status=status.HTTP_400_BAD_REQUEST)
        outcome = services.process_event(
            provider="stripe", event=json.loads(json.dumps(event, default=str))
        )
        return Response({"result": outcome})
