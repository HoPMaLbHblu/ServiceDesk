from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import PublicIdModel, TenantModel

MONEY = {"max_digits": 12, "decimal_places": 2}


class InvoiceStatus(models.TextChoices):
    ISSUED = "issued", "Issued"
    VOID = "void", "Void"


class Invoice(PublicIdModel, TenantModel):
    """Issued invoice. Lines and party details are snapshots and never change after issue."""

    order = models.ForeignKey(
        "orders.RepairOrder", on_delete=models.PROTECT, related_name="invoices"
    )
    estimate = models.ForeignKey(
        "estimates.Estimate", null=True, on_delete=models.PROTECT, related_name="+"
    )
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.ISSUED
    )
    currency = models.CharField(max_length=3)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    subtotal = models.DecimalField(**MONEY)
    tax_total = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    amount_paid = models.DecimalField(**MONEY, default=Decimal("0.00"))
    issued_at = models.DateTimeField()
    due_date = models.DateField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    business_snapshot = models.JSONField(default=dict)
    customer_snapshot = models.JSONField(default=dict)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"], name="invoice_number_unique_per_business"
            ),
            models.UniqueConstraint(
                fields=["order"], condition=Q(status="issued"), name="invoice_one_issued_per_order"
            ),
            models.CheckConstraint(
                condition=Q(total=F("subtotal") + F("tax_total")), name="invoice_total_consistent"
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__gte=0), name="invoice_paid_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(amount_paid__lte=F("total")), name="invoice_not_overpaid"
            ),
        ]

    def __str__(self) -> str:
        return self.reference

    @property
    def reference(self) -> str:
        return f"INV-{self.number:05d}"

    @property
    def balance_due(self) -> Decimal:
        return self.total - self.amount_paid


class InvoiceLine(TenantModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    position = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10)
    sku = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(**MONEY)
    taxable = models.BooleanField(default=True)
    line_total = models.DecimalField(**MONEY)

    class Meta:
        ordering = ["position", "id"]


class PaymentKind(models.TextChoices):
    PAYMENT = "payment", "Payment"
    REFUND = "refund", "Refund"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card (terminal)"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    OTHER = "other", "Other"


class PaymentSource(models.TextChoices):
    # Staff recorded a payment the business received outside ServiceDesk.
    RECORDED = "recorded", "Recorded by staff"
    # Reserved for payments confirmed by a provider webhook. Not used yet:
    # repair-order payments are not processed online (see docs/limitations.md).
    PROVIDER = "provider", "Processed by payment provider"


class Payment(PublicIdModel, TenantModel):
    """Append-only money movement against an invoice. Refunds are separate rows."""

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(max_length=10, choices=PaymentKind.choices)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    source = models.CharField(
        max_length=10, choices=PaymentSource.choices, default=PaymentSource.RECORDED
    )
    amount = models.DecimalField(**MONEY)
    received_at = models.DateTimeField()
    reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    refund_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds"
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    idempotency_key = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["received_at", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(
                condition=Q(kind="payment", refund_of__isnull=True)
                | Q(kind="refund", refund_of__isnull=False),
                name="payment_refund_references_payment",
            ),
            models.UniqueConstraint(
                fields=["business", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="payment_idempotency_key_unique",
            ),
        ]
