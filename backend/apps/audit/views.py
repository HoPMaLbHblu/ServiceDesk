from rest_framework import mixins, serializers, viewsets

from apps.core.api import TenantViewMixin
from apps.core.tenancy import OWNER

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_label",
            "action",
            "entity_type",
            "entity_id",
            "entity_label",
            "changes",
            "request_id",
            "created_at",
        ]


class AuditLogViewSet(TenantViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only. There is no endpoint that changes audit records."""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    filterset_fields = {
        "action": ["exact", "startswith"],
        "entity_type": ["exact"],
        "created_at": ["date__gte", "date__lte"],
    }
    search_fields = ["entity_label", "actor_label", "action"]
    ordering = ["-created_at", "-id"]
    role_rules = {"*": OWNER}
