from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel


class NotificationKind(models.TextChoices):
    EMAIL_VERIFICATION = "email_verification", "Email verification"
    PASSWORD_RESET = "password_reset", "Password reset"
    INVITATION = "invitation", "Staff invitation"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation", "Appointment confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder", "Appointment reminder"
    ESTIMATE_APPROVAL_REQUEST = "estimate_approval_request", "Estimate approval request"
    ORDER_STATUS = "order_status", "Repair status update"
    LOW_STOCK = "low_stock", "Low-stock alert"
    PORTAL_ACCESS = "portal_access", "Customer portal access"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class Notification(TimeStampedModel):
    """Transactional outbox row for one email.

    Rows are written in the same transaction as the change that causes them.
    A worker delivers them after commit; a periodic relay picks up anything the
    broker lost. ``idempotency_key`` makes sure one event yields one email.
    """

    business = models.ForeignKey(
        "businesses.Business", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField(max_length=40, choices=NotificationKind.choices)
    recipient_email = models.EmailField()
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    # Bodies with one-time links are blanked after delivery so the database
    # does not keep usable secrets.
    contains_secret = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    entity_type = models.CharField(max_length=80, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["business", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(attempts__lte=models.F("max_attempts")),
                name="notification_attempts_bounded",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} to {self.recipient_email} ({self.status})"
