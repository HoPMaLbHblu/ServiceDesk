"""Shared building blocks for tenant-scoped API views and serializers."""

from rest_framework import serializers, viewsets

from .tenancy import HasWorkspaceRole, require_tenant


class TenantViewMixin:
    """Scopes every queryset to the active business.

    Lookups of records from another business behave exactly like records that
    do not exist (404), so ids from other tenants reveal nothing.
    """

    permission_classes = [HasWorkspaceRole]
    role_rules: dict = {}

    @property
    def tenant(self):
        return require_tenant(self.request)

    def get_queryset(self):
        return super().get_queryset().filter(business=self.tenant.business)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request and self.request.user.is_authenticated:
            context["tenant"] = require_tenant(self.request)
        return context


class TenantModelViewSet(TenantViewMixin, viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(business=self.tenant.business)


class TenantRelatedField(serializers.SlugRelatedField):
    """Relation field that only accepts records of the active business.

    Uses ``public_id`` when the model has one, otherwise the primary key.
    A record from another business is reported as "does not exist".
    """

    def __init__(self, model=None, slug_field="public_id", **kwargs):
        self.model = model
        kwargs.setdefault("queryset", model.objects.all() if model is not None else None)
        super().__init__(slug_field=slug_field, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant = self.context.get("tenant")
        if tenant is None:
            return queryset.none()
        return queryset.filter(business=tenant.business)

    def to_representation(self, obj):
        return str(getattr(obj, self.slug_field))


class TenantSerializerMixin:
    @property
    def tenant(self):
        return self.context["tenant"]
