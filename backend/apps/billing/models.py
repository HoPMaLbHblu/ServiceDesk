from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Plan(TimeStampedModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    # None means unlimited.
    max_staff = models.PositiveIntegerField(null=True, blank=True)
    max_orders_per_month = models.PositiveIntegerField(null=True, blank=True)
    stripe_price_id = models.CharField(max_length=120, blank=True)
    is_public = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_monthly"]

    def __str__(self) -> str:
        return self.name


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trial"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELLED = "cancelled", "Cancelled"


class Subscription(TimeStampedModel):
    business = models.OneToOneField(
        "businesses.Business", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(
        max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    past_due_since = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=20, default="dev")
    provider_customer_id = models.CharField(max_length=120, blank=True, db_index=True)
    provider_subscription_id = models.CharField(max_length=120, blank=True, db_index=True)

    def __str__(self) -> str:
        return f"{self.business} on {self.plan} ({self.status})"


class BillingEventStatus(models.TextChoices):
    PROCESSED = "processed", "Processed"
    IGNORED = "ignored", "Ignored"
    FAILED = "failed", "Failed"


class BillingEvent(TimeStampedModel):
    """Provider webhook event. The unique id makes processing idempotent."""

    provider = models.CharField(max_length=20)
    event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=120)
    business = models.ForeignKey(
        "businesses.Business", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=BillingEventStatus.choices)
    error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="billing_event_unique"),
        ]
