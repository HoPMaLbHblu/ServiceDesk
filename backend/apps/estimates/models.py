from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import PublicIdModel, TenantModel, TimeStampedModel

MONEY = {"max_digits": 12, "decimal_places": 2}


class EstimateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent to customer"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SUPERSEDED = "superseded", "Superseded"


class DecisionChannel(models.TextChoices):
    PORTAL = "portal", "Customer portal"
    LINK = "link", "Approval link"
    STAFF = "staff", "Recorded by staff on the customer's behalf"


class Estimate(PublicIdModel, TenantModel):
    """One version of the price quote for a repair order.

    Once sent, a version's lines are frozen. Changing the quote means creating
    a new version, which supersedes the old one and needs its own approval.
    """

    order = models.ForeignKey(
        "orders.RepairOrder", on_delete=models.CASCADE, related_name="estimates"
    )
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=EstimateStatus.choices, default=EstimateStatus.DRAFT
    )
    notes = models.TextField(blank=True, help_text="Shown to the customer.")
    currency = models.CharField(max_length=3)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    subtotal = models.DecimalField(**MONEY, default=Decimal("0.00"))
    tax_total = models.DecimalField(**MONEY, default=Decimal("0.00"))
    total = models.DecimalField(**MONEY, default=Decimal("0.00"))
    sent_at = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    # SHA-256 of the frozen content when sent; an approval must match it.
    content_hash = models.CharField(max_length=64, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by_name = models.CharField(max_length=200, blank=True)
    decision_channel = models.CharField(max_length=10, choices=DecisionChannel.choices, blank=True)
    decision_note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["order", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["order", "version"], name="estimate_unique_version"),
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status__in=["draft", "sent"]),
                name="estimate_one_open_version_per_order",
            ),
            models.CheckConstraint(
                condition=Q(total=models.F("subtotal") + models.F("tax_total")),
                name="estimate_total_consistent",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["approved", "rejected"]) | Q(decided_at__isnull=False),
                name="estimate_decision_has_timestamp",
            ),
        ]

    def __str__(self) -> str:
        return f"Estimate v{self.version} for {self.order}"


class LineKind(models.TextChoices):
    LABOR = "labor", "Labor"
    PART = "part", "Part"
    FEE = "fee", "Fee"


class EstimateLine(TenantModel):
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=LineKind.choices)
    # Snapshot of the catalog part at the time the line was written.
    part = models.ForeignKey(
        "inventory.Part", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sku = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(**MONEY)
    taxable = models.BooleanField(default=True)
    line_total = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="estimate_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="estimate_line_price_non_negative"
            ),
        ]


class ApprovalLink(TimeStampedModel):
    """Emailed link that lets the customer decide on exactly one estimate version."""

    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="approval_links")
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
