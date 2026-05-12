from rest_framework import serializers

from apps.core.api import StaffUserField, TenantRelatedField
from apps.customers.models import Customer, Device

from . import workflow
from .models import Attachment, OrderEvent, OrderStatus, Priority, RepairOrder


class PersonRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    name = serializers.CharField(source="full_name")


class OrderListSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    reference = serializers.CharField(read_only=True)
    customer = PersonRefSerializer(read_only=True)
    device_label = serializers.CharField(source="device.__str__", read_only=True)
    assigned_technician = PersonRefSerializer(read_only=True, allow_null=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RepairOrder
        fields = [
            "id",
            "number",
            "reference",
            "customer",
            "device_label",
            "status",
            "status_label",
            "payment_status",
            "priority",
            "assigned_technician",
            "expected_completion_date",
            "created_at",
            "updated_at",
        ]


class DeviceRefSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id")

    class Meta:
        model = Device
        fields = ["id", "kind", "brand", "model", "serial_number", "imei", "color"]


class CustomerContactSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id")
    name = serializers.CharField(source="full_name")

    class Meta:
        model = Customer
        fields = ["id", "name", "email", "phone"]


class OrderDetailSerializer(OrderListSerializer):
    customer = CustomerContactSerializer(read_only=True)
    device = DeviceRefSerializer(read_only=True)
    diagnosed_by = PersonRefSerializer(read_only=True, allow_null=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta(OrderListSerializer.Meta):
        fields = OrderListSerializer.Meta.fields + [
            "device",
            "problem_description",
            "diagnostic_findings",
            "diagnosed_at",
            "diagnosed_by",
            "source",
            "status_changed_at",
            "completed_at",
            "cancelled_at",
            "cancellation_reason",
            "version",
            "allowed_transitions",
        ]

    def get_allowed_transitions(self, order) -> list[str]:
        tenant = self.context.get("tenant")
        request = self.context.get("request")
        if tenant is None or request is None:
            return []
        return workflow.allowed_for(order, tenant, request.user)


class OrderCreateSerializer(serializers.Serializer):
    customer = TenantRelatedField(model=Customer)
    device = TenantRelatedField(model=Device)
    problem_description = serializers.CharField()
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.NORMAL)
    assigned_technician = StaffUserField(required=False, allow_null=True)
    expected_completion_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["device"].customer_id != attrs["customer"].pk:
            raise serializers.ValidationError(
                {"device": ["Choose one of this customer's devices."]}
            )
        return attrs


class OrderUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(
        help_text="Version the client last saw; a mismatch returns 409."
    )
    problem_description = serializers.CharField(required=False)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    assigned_technician = StaffUserField(required=False, allow_null=True)
    expected_completion_date = serializers.DateField(required=False, allow_null=True)


class TransitionSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=OrderStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class DiagnosticsSerializer(serializers.Serializer):
    findings = serializers.CharField()


class NoteCreateSerializer(serializers.Serializer):
    body = serializers.CharField()
    visible_to_customer = serializers.BooleanField(default=False)


class OrderEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderEvent
        fields = [
            "id",
            "kind",
            "actor_label",
            "message",
            "visible_to_customer",
            "from_status",
            "to_status",
            "data",
            "created_at",
        ]


class AttachmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = Attachment
        fields = [
            "id",
            "original_name",
            "content_type",
            "size",
            "caption",
            "visible_to_customer",
            "uploaded_by_name",
            "created_at",
        ]


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    caption = serializers.CharField(required=False, allow_blank=True, default="")
    visible_to_customer = serializers.BooleanField(default=False)
