import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublicIdModel(models.Model):
    """Exposes a UUID in URLs. The UUID is an identifier, never an authorization."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        abstract = True


class TenantModel(TimeStampedModel):
    """Base for every record owned by a business (shared-schema tenancy)."""

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True
