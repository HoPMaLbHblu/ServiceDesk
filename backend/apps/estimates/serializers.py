from decimal import Decimal

from rest_framework import serializers

from apps.core.api import TenantRelatedField
from apps.inventory.models import Part
from apps.orders.models import RepairOrder

from .models import Estimate, EstimateLine, LineKind


class EstimateLineSerializer(serializers.ModelSerializer):
    part = serializers.UUIDField(
        source="part.public_id", read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = EstimateLine
        fields = [
            "id",
            "position",
            "kind",
            "part",
            "sku",
            "description",
            "quantity",
            "unit_price",
            "taxable",
            "line_total",
        ]


class EstimateSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    order = serializers.UUIDField(source="order.public_id", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    lines = EstimateLineSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Estimate
        fields = [
            "id",
            "order",
            "order_reference",
            "version",
            "status",
            "status_label",
            "notes",
            "currency",
            "tax_rate",
            "subtotal",
            "tax_total",
            "total",
            "sent_at",
            "valid_until",
            "content_hash",
            "decided_at",
            "decided_by_name",
            "decision_channel",
            "decision_note",
            "lines",
            "created_at",
            "updated_at",
        ]


class EstimateCreateSerializer(serializers.Serializer):
    order = TenantRelatedField(model=RepairOrder)


class LineInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LineKind.choices, required=False)
    part = TenantRelatedField(model=Part, required=False, allow_null=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    taxable = serializers.BooleanField(default=True)


class ReplaceLinesSerializer(serializers.Serializer):
    lines = LineInputSerializer(many=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class DecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(required=False, allow_blank=True, default="")
    # Hash of the version the customer reviewed; protects against approving changed content.
    content_hash = serializers.CharField(required=False, allow_blank=True)


class StaffDecisionSerializer(DecisionSerializer):
    customer_name = serializers.CharField(
        max_length=200, help_text="Who gave the decision, e.g. by phone."
    )


class PublicDecisionSerializer(DecisionSerializer):
    name = serializers.CharField(max_length=200)


class PublicEstimateSerializer(serializers.Serializer):
    """What the customer sees through an approval link or the portal."""

    id = serializers.UUIDField(source="public_id")
    business_name = serializers.CharField(source="business.name")
    order_reference = serializers.CharField(source="order.reference")
    device = serializers.CharField(source="order.device.__str__")
    customer_name = serializers.CharField(source="order.customer.full_name")
    version = serializers.IntegerField()
    status = serializers.CharField()
    notes = serializers.CharField()
    currency = serializers.CharField()
    tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    tax_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    valid_until = serializers.DateField()
    content_hash = serializers.CharField()
    decided_at = serializers.DateTimeField()
    decided_by_name = serializers.CharField()
    lines = serializers.SerializerMethodField()
    link_state = serializers.CharField(required=False)

    def get_lines(self, estimate) -> list[dict]:
        return [
            {
                "kind": line.kind,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
                "taxable": line.taxable,
            }
            for line in estimate.lines.all()
        ]
