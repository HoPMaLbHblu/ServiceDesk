"""Subscription state, plan enforcement and provider event processing.

Platform subscription billing (a business paying for ServiceDesk) is entirely
separate from repair-order payments (customers paying a business).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import PlanLimitExceeded

from .models import BillingEvent, BillingEventStatus, Plan, Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)

DEFAULT_PLAN_CODE = "starter"


@dataclass(frozen=True)
class AccessState:
    can_write: bool
    reason: str = ""


def start_trial(business) -> Subscription:
    plan = Plan.objects.get(code=DEFAULT_PLAN_CODE)
    return Subscription.objects.create(
        business=business,
        plan=plan,
        status=SubscriptionStatus.TRIALING,
        trial_ends_at=timezone.now() + timedelta(days=settings.BILLING_TRIAL_DAYS),
        provider=settings.BILLING_PROVIDER,
    )


def access_state(subscription: Subscription | None, now: datetime | None = None) -> AccessState:
    """Whether a business may create or change records.

    - Trial: allowed until ``trial_ends_at``.
    - Active: allowed.
    - Past due: allowed for ``BILLING_PAST_DUE_GRACE_DAYS`` after the first failed payment.
    - Cancelled, expired trial, or grace period over: read-only. Owners can still
      reach billing to fix it, and data stays readable and exportable.
    """
    now = now or timezone.now()
    if subscription is None:
        return AccessState(False, "This workspace has no subscription.")
    if subscription.status == SubscriptionStatus.ACTIVE:
        return AccessState(True)
    if subscription.status == SubscriptionStatus.TRIALING:
        if subscription.trial_ends_at and subscription.trial_ends_at > now:
            return AccessState(True)
        return AccessState(False, "The free trial has ended. Choose a plan to keep working.")
    if subscription.status == SubscriptionStatus.PAST_DUE:
        since = subscription.past_due_since or now
        if since + timedelta(days=settings.BILLING_PAST_DUE_GRACE_DAYS) > now:
            return AccessState(True)
        return AccessState(False, "Payment is overdue. Update billing details to keep working.")
    return AccessState(False, "The subscription is cancelled. Choose a plan to keep working.")


def subscription_for(business) -> Subscription | None:
    return Subscription.objects.select_related("plan").filter(business=business).first()


def assert_can_write(business) -> None:
    state = access_state(subscription_for(business))
    if not state.can_write:
        raise PlanLimitExceeded(state.reason, code="subscription_inactive")


def assert_staff_limit(business, adding: int = 1) -> None:
    from apps.businesses.models import Invitation, Membership

    subscription = subscription_for(business)
    if subscription is None or subscription.plan.max_staff is None:
        return
    active = Membership.objects.filter(business=business, is_active=True).count()
    pending = Invitation.objects.filter(
        business=business,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).count()
    if active + pending + adding > subscription.plan.max_staff:
        raise PlanLimitExceeded(
            f"The {subscription.plan.name} plan allows {subscription.plan.max_staff} team members "
            "including pending invitations.",
            code="staff_limit_reached",
            details={"limit": subscription.plan.max_staff, "used": active + pending},
        )


def assert_order_limit(business) -> None:
    from apps.orders.models import RepairOrder

    subscription = subscription_for(business)
    if subscription is None or subscription.plan.max_orders_per_month is None:
        return
    tz = business.tzinfo
    local_now = timezone.now().astimezone(tz)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    used = RepairOrder.objects.filter(business=business, created_at__gte=month_start).count()
    if used >= subscription.plan.max_orders_per_month:
        raise PlanLimitExceeded(
            f"The {subscription.plan.name} plan allows {subscription.plan.max_orders_per_month} "
            "new repair orders per month.",
            code="order_limit_reached",
            details={"limit": subscription.plan.max_orders_per_month, "used": used},
        )


# --- Provider events -------------------------------------------------------

STRIPE_STATUS_MAP = {
    "trialing": SubscriptionStatus.TRIALING,
    "active": SubscriptionStatus.ACTIVE,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "incomplete": SubscriptionStatus.PAST_DUE,
    "canceled": SubscriptionStatus.CANCELLED,
    "incomplete_expired": SubscriptionStatus.CANCELLED,
}


def _from_unix(value) -> datetime:
    return datetime.fromtimestamp(int(value), tz=UTC)


def process_event(*, provider: str, event: dict) -> str:
    """Apply one provider event exactly once.

    Returns ``processed``, ``ignored`` or ``duplicate``. The (provider, event id)
    unique constraint is the idempotency guard: a redelivered event inserts
    nothing and changes nothing.
    """
    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    if not event_id or not event_type:
        raise ValueError("Event id and type are required.")
    try:
        with transaction.atomic():
            record = BillingEvent.objects.create(
                provider=provider,
                event_id=event_id,
                event_type=event_type,
                payload=event,
                status=BillingEventStatus.IGNORED,
            )
            outcome = _apply(record, event)
            record.status = outcome
            record.processed_at = timezone.now()
            record.save(update_fields=["status", "processed_at", "business", "updated_at"])
            return outcome
    except IntegrityError:
        if BillingEvent.objects.filter(provider=provider, event_id=event_id).exists():
            return "duplicate"
        raise


def _locate_subscription(obj: dict) -> Subscription | None:
    metadata = obj.get("metadata") or {}
    business_ref = metadata.get("business_id") or obj.get("client_reference_id")
    queryset = Subscription.objects.select_for_update().select_related("plan", "business")
    if business_ref:
        found = queryset.filter(business__public_id=business_ref).first()
        if found:
            return found
    subscription_id = (
        obj.get("subscription") if obj.get("object") != "subscription" else obj.get("id")
    )
    if subscription_id:
        found = queryset.filter(provider_subscription_id=subscription_id).first()
        if found:
            return found
    customer_id = obj.get("customer")
    if customer_id:
        return queryset.filter(provider_customer_id=customer_id).first()
    return None


def _plan_from(obj: dict) -> Plan | None:
    metadata = obj.get("metadata") or {}
    if metadata.get("plan_code"):
        return Plan.objects.filter(code=metadata["plan_code"]).first()
    items = ((obj.get("items") or {}).get("data")) or []
    for item in items:
        price_id = (item.get("price") or {}).get("id")
        if price_id:
            plan = Plan.objects.filter(stripe_price_id=price_id).first()
            if plan:
                return plan
    return None


def _apply(record: BillingEvent, event: dict) -> str:
    obj = (event.get("data") or {}).get("object") or {}
    subscription = _locate_subscription(obj)
    if subscription is None:
        logger.info("billing_event_unmatched", extra={"event_type": record.event_type})
        return BillingEventStatus.IGNORED
    record.business = subscription.business

    created = event.get("created")
    event_at = _from_unix(created) if created else timezone.now()
    if subscription.last_event_at and event_at < subscription.last_event_at:
        # Stripe does not guarantee ordering; an older event must not undo a newer one.
        return BillingEventStatus.IGNORED

    old_status = subscription.status
    now = timezone.now()
    event_type = record.event_type

    if event_type == "checkout.session.completed":
        subscription.provider_customer_id = obj.get("customer") or subscription.provider_customer_id
        subscription.provider_subscription_id = (
            obj.get("subscription") or subscription.provider_subscription_id
        )
        plan = _plan_from(obj)
        if plan:
            subscription.plan = plan
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.past_due_since = None
        subscription.cancelled_at = None
    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        subscription.provider_subscription_id = (
            obj.get("id") or subscription.provider_subscription_id
        )
        subscription.provider_customer_id = obj.get("customer") or subscription.provider_customer_id
        mapped = STRIPE_STATUS_MAP.get(obj.get("status", ""))
        if mapped:
            subscription.status = mapped
        plan = _plan_from(obj)
        if plan:
            subscription.plan = plan
        period_end = obj.get("current_period_end")
        if period_end:
            subscription.current_period_end = _from_unix(period_end)
        subscription.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
    elif event_type == "customer.subscription.deleted":
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = now
    elif event_type == "invoice.payment_failed":
        subscription.status = SubscriptionStatus.PAST_DUE
    elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
        subscription.status = SubscriptionStatus.ACTIVE
    else:
        return BillingEventStatus.IGNORED

    if (
        subscription.status == SubscriptionStatus.PAST_DUE
        and old_status != SubscriptionStatus.PAST_DUE
    ):
        subscription.past_due_since = now
    elif subscription.status != SubscriptionStatus.PAST_DUE:
        subscription.past_due_since = None
    subscription.last_event_at = event_at
    subscription.save()

    if old_status != subscription.status:
        from apps.audit.services import record as audit

        audit(
            action="subscription.status_changed",
            entity=subscription,
            business=subscription.business,
            changes={"status": [old_status, subscription.status], "event": record.event_type},
        )
    return BillingEventStatus.PROCESSED
