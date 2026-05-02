from rest_framework import serializers

from .models import CURRENCY_CHOICES, Business, Invitation, Membership, Role, validate_timezone


class BusinessSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = Business
        fields = [
            "id",
            "name",
            "slug",
            "timezone",
            "currency",
            "tax_rate",
            "default_labor_rate",
            "estimate_valid_days",
            "email",
            "phone",
            "address",
            "created_at",
        ]
        read_only_fields = ["slug", "created_at"]

    def validate_timezone(self, value):
        validate_timezone(value)
        return value


class CreateBusinessSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    timezone = serializers.CharField(max_length=64, default="UTC")
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, default="USD")
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=0, max_value=100, default=0
    )
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_timezone(self, value):
        validate_timezone(value)
        return value


class WorkspaceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="business.public_id")
    name = serializers.CharField(source="business.name")
    role = serializers.CharField()


class SwitchWorkspaceSerializer(serializers.Serializer):
    business_id = serializers.UUIDField()


class MemberSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(read_only=True)
    user_id = serializers.UUIDField(source="user.public_id", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "full_name", "email", "role", "is_active", "created_at"]
        read_only_fields = ["is_active", "created_at"]


class ChangeRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)


class InvitationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    status = serializers.CharField(read_only=True)
    invited_by_name = serializers.CharField(
        source="invited_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "status", "expires_at", "invited_by_name", "created_at"]
        read_only_fields = ["expires_at", "created_at"]


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices)


class InvitationTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class InvitationPreviewSerializer(serializers.Serializer):
    business_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    status = serializers.CharField()


class StaffOptionSerializer(serializers.Serializer):
    """Minimal staff record used to pick a technician."""

    user_id = serializers.UUIDField(source="user.public_id")
    full_name = serializers.CharField(source="user.full_name")
    role = serializers.CharField()
