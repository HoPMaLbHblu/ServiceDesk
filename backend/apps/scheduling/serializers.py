from rest_framework import serializers

from apps.core.api import StaffUserField, TenantRelatedField
from apps.customers.models import Customer
from apps.orders.models import RepairOrder

from .models import (
    Appointment,
    AppointmentKind,
    AppointmentStatus,
    BusinessHours,
    TechnicianAvailability,
    TimeOff,
)


class AppointmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    customer = serializers.UUIDField(source="customer.public_id", read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    technician = serializers.UUIDField(source="technician.public_id", read_only=True)
    technician_name = serializers.CharField(source="technician.full_name", read_only=True)
    order = serializers.UUIDField(
        source="order.public_id", read_only=True, allow_null=True, default=None
    )
    order_reference = serializers.CharField(source="order.reference", read_only=True, default=None)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "customer",
            "customer_name",
            "technician",
            "technician_name",
            "order",
            "order_reference",
            "kind",
            "kind_label",
            "starts_at",
            "ends_at",
            "status",
            "notes",
            "cancellation_reason",
            "created_at",
        ]


class BookSerializer(serializers.Serializer):
    customer = TenantRelatedField(model=Customer)
    technician = StaffUserField()
    order = TenantRelatedField(model=RepairOrder, required=False, allow_null=True)
    kind = serializers.ChoiceField(
        choices=AppointmentKind.choices, default=AppointmentKind.DIAGNOSIS
    )
    starts_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=15, max_value=480)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class RescheduleSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=15, max_value=480)
    technician = StaffUserField(required=False)


class AppointmentStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            (s, label) for s, label in AppointmentStatus.choices if s != AppointmentStatus.SCHEDULED
        ]
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AvailabilityQuerySerializer(serializers.Serializer):
    technician = StaffUserField()
    date = serializers.DateField()
    duration_minutes = serializers.IntegerField(min_value=15, max_value=480, default=60)


class BusinessHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessHours
        fields = ["weekday", "opens_at", "closes_at", "is_closed"]

    def validate(self, attrs):
        if not attrs.get("is_closed"):
            opens, closes = attrs.get("opens_at"), attrs.get("closes_at")
            if opens is None or closes is None:
                raise serializers.ValidationError(
                    {"opens_at": ["Set opening and closing times or mark the day closed."]}
                )
            if closes <= opens:
                raise serializers.ValidationError(
                    {"closes_at": ["Closing time must be after opening time."]}
                )
        return attrs


class TechnicianAvailabilitySerializer(serializers.ModelSerializer):
    technician = StaffUserField()
    technician_name = serializers.CharField(source="technician.full_name", read_only=True)

    class Meta:
        model = TechnicianAvailability
        fields = ["id", "technician", "technician_name", "weekday", "start_time", "end_time"]

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": ["End must be after start."]})
        if not 0 <= attrs["weekday"] <= 6:
            raise serializers.ValidationError({"weekday": ["0 (Monday) to 6 (Sunday)."]})
        return attrs


class TimeOffSerializer(serializers.ModelSerializer):
    technician = StaffUserField()
    technician_name = serializers.CharField(source="technician.full_name", read_only=True)

    class Meta:
        model = TimeOff
        fields = ["id", "technician", "technician_name", "starts_at", "ends_at", "reason"]

    def validate(self, attrs):
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": ["End must be after start."]})
        return attrs
