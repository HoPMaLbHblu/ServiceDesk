from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only record of important actions.

    Updates and deletes are blocked by a PostgreSQL trigger (see migration 0002),
    by ``save`` below, and by the read-only admin.
    """

    business = models.ForeignKey(
        "businesses.Business", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Kept so the record stays readable if the user is later deleted.
    actor_label = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80)
    entity_id = models.CharField(max_length=64)
    entity_label = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["business", "-created_at"]),
            models.Index(fields=["business", "entity_type", "entity_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}:{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("Audit records are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit records are append-only.")
