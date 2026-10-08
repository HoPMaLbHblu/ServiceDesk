from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.core.api import TenantRelatedField
from apps.orders.models import RepairOrder

from .models import Invoice, InvoiceLine, Payment, PaymentMethod


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "position",
            "kind",
            "sku",
            "description",
            "quantity",
            "unit_price",
            "taxable",
            "line_total",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    refund_of = serializers.UUIDField(
        source="refund_of.public_id", read_only=True, allow_null=True, default=None
    )
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True, default=""
    )
    refundable = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "kind",
            "method",
            "source",
            "amount",
            "received_at",
            "reference",
            "note",
            "refund_of",
            "recorded_by_name",
            "refundable",
            "created_at",
        ]

    def get_refundable(self, payment) -> str:
        if payment.kind != "payment":
            return "0.00"
        refunded = sum((r.amount for r in payment.refunds.all()), start=type(payment.amount)("0"))
        return str(payment.amount - refunded)


class InvoiceListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    reference = serializers.CharField(read_only=True)
    order = serializers.UUIDField(source="order.public_id", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    customer_name = serializers.SerializerMethodField()
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(source="order.payment_status", read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "reference",
            "order",
            "order_reference",
            "customer_name",
            "status",
            "currency",
            "total",
            "amount_paid",
            "balance_due",
            "payment_status",
            "issued_at",
            "due_date",
            "is_overdue",
        ]

    def get_is_overdue(self, invoice) -> bool:
        """Issued, not fully paid, and the due date has passed in the shop's timezone."""
        if (
            invoice.status != "issued"
            or invoice.amount_paid >= invoice.total
            or not invoice.due_date
        ):
            return False
        return invoice.due_date < timezone.now().astimezone(invoice.business.tzinfo).date()

    def get_customer_name(self, invoice) -> str:
        return invoice.customer_snapshot.get("name", "")


class InvoiceDetailSerializer(InvoiceListSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    estimate_version = serializers.IntegerField(
        source="estimate.version", read_only=True, default=None
    )

    class Meta(InvoiceListSerializer.Meta):
        fields = InvoiceListSerializer.Meta.fields + [
            "tax_rate",
            "subtotal",
            "tax_total",
            "business_snapshot",
            "customer_snapshot",
            "notes",
            "void_reason",
            "voided_at",
            "estimate_version",
            "lines",
            "payments",
        ]


class IssueInvoiceSerializer(serializers.Serializer):
    order = TenantRelatedField(model=RepairOrder)
    due_days = serializers.IntegerField(min_value=0, max_value=365, default=14)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField()


class RecordPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    received_at = serializers.DateTimeField(required=False)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )

    def validate_received_at(self, value):
        # A few minutes of slack covers clocks that run slightly ahead of the server.
        if value > timezone.now() + timedelta(minutes=5):
            raise serializers.ValidationError("A payment cannot be dated in the future.")
        return value


class RefundSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = serializers.CharField()
    method = serializers.ChoiceField(choices=PaymentMethod.choices, required=False)
    idempotency_key = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
