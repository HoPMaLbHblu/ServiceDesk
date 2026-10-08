from decimal import Decimal

from rest_framework import serializers

from apps.core.api import TenantRelatedField
from apps.orders.models import RepairOrder

from .models import Part, PartReservation, StockMovement


class PartSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    quantity_available = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    initial_quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        write_only=True,
        required=False,
        help_text="Opening stock, recorded as a receipt movement.",
    )

    class Meta:
        model = Part
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "unit",
            "purchase_cost",
            "selling_price",
            "low_stock_threshold",
            "quantity_on_hand",
            "quantity_reserved",
            "quantity_available",
            "is_low_stock",
            "is_active",
            "initial_quantity",
            "created_at",
            "updated_at",
        ]
        # Stock levels change only through receipts, adjustments, reservations and consumption.
        read_only_fields = ["quantity_on_hand", "quantity_reserved", "created_at", "updated_at"]
        extra_kwargs = {
            "purchase_cost": {"min_value": 0},
            "selling_price": {"min_value": 0},
            "low_stock_threshold": {"min_value": 0},
        }

    def validate_sku(self, value):
        value = value.strip().upper()
        tenant = self.context["tenant"]
        clash = Part.objects.filter(business=tenant.business, sku=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("Another part already uses this SKU.")
        return value


class ReceiveStockSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unit_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdjustStockSerializer(serializers.Serializer):
    counted_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
    reason = serializers.CharField()


class StockMovementSerializer(serializers.ModelSerializer):
    part = serializers.UUIDField(source="part.public_id", read_only=True)
    part_name = serializers.CharField(source="part.name", read_only=True)
    sku = serializers.CharField(source="part.sku", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True, default=None)
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default="")

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "part",
            "part_name",
            "sku",
            "kind",
            "on_hand_delta",
            "reserved_delta",
            "on_hand_after",
            "reserved_after",
            "unit_cost",
            "order_reference",
            "reason",
            "actor_name",
            "created_at",
        ]


class ReservationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    order = serializers.UUIDField(source="order.public_id", read_only=True)
    part = serializers.UUIDField(source="part.public_id", read_only=True)
    part_name = serializers.CharField(source="part.name", read_only=True)
    sku = serializers.CharField(source="part.sku", read_only=True)
    unit = serializers.CharField(source="part.unit", read_only=True)

    class Meta:
        model = PartReservation
        fields = [
            "id",
            "order",
            "part",
            "part_name",
            "sku",
            "unit",
            "quantity",
            "status",
            "consumed_at",
            "released_at",
            "created_at",
        ]


class ReserveSerializer(serializers.Serializer):
    order = TenantRelatedField(model=RepairOrder)
    part = TenantRelatedField(model=Part)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    idempotency_key = serializers.CharField(max_length=80)
