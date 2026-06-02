from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import TenantViewMixin
from apps.core.tenancy import MANAGERS

from . import services
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    body = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "recipient_email",
            "subject",
            "body",
            "status",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "last_error",
            "sent_at",
            "created_at",
        ]

    def get_body(self, notification) -> str:
        if notification.contains_secret:
            return "[Contains a one-time link. Content hidden.]"
        return notification.body


class NotificationViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Delivery log of emails sent on behalf of the workspace."""

    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    filterset_fields = ["status", "kind"]
    search_fields = ["recipient_email", "subject"]
    ordering = ["-created_at"]
    role_rules = {"*": MANAGERS}

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        notification = services.retry(self.get_object())
        return Response(NotificationSerializer(notification).data)
