from rest_framework import serializers

from apps.core.api import TenantRelatedField

from .models import Customer, CustomerNote, CustomerPortalAccess, Device


class DeviceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    customer = TenantRelatedField(model=Customer)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "customer",
            "customer_name",
            "kind",
            "brand",
            "model",
            "serial_number",
            "imei",
            "color",
            "notes",
            "label",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_customer(self, customer):
        if self.instance is not None and customer != self.instance.customer:
            raise serializers.ValidationError("A device cannot be moved to another customer.")
        return customer


class CustomerSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    device_count = serializers.IntegerField(read_only=True, default=0)
    open_order_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Customer
        fields = [
            "id",
            "full_name",
            "company",
            "email",
            "phone",
            "address",
            "customer_notes",
            "marketing_opt_in",
            "is_archived",
            "device_count",
            "open_order_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        email = attrs.get("email", getattr(self.instance, "email", ""))
        phone = attrs.get("phone", getattr(self.instance, "phone", ""))
        if not email and not phone:
            raise serializers.ValidationError(
                {"phone": ["Add a phone number or an email address."]}
            )
        return attrs


class CustomerNoteSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="")

    class Meta:
        model = CustomerNote
        fields = ["id", "body", "author_name", "created_at"]
        read_only_fields = ["created_at"]


class PortalAccessSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = CustomerPortalAccess
        fields = ["id", "email", "full_name", "created_at"]


class PortalInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()


class RevokePortalSerializer(serializers.Serializer):
    access_id = serializers.IntegerField()
