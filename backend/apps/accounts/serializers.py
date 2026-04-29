from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    email_verified = serializers.BooleanField(source="is_email_verified", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "email_verified"]
        read_only_fields = ["email"]


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], full_name=attrs["full_name"])
        password_validation.validate_password(attrs["password"], candidate)
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    new_password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value


class MembershipSummarySerializer(serializers.Serializer):
    business_id = serializers.UUIDField()
    business_name = serializers.CharField()
    role = serializers.CharField()


class PortalLinkSummarySerializer(serializers.Serializer):
    business_id = serializers.UUIDField()
    business_name = serializers.CharField()
    customer_id = serializers.UUIDField()
    customer_name = serializers.CharField()


class ActiveWorkspaceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    timezone = serializers.CharField()
    currency = serializers.CharField()


class SessionSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    user = UserSerializer(allow_null=True)
    memberships = MembershipSummarySerializer(many=True)
    portal_links = PortalLinkSummarySerializer(many=True)
    active_workspace = ActiveWorkspaceSerializer(allow_null=True)
