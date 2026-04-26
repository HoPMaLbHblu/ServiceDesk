import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Notification, NotificationStatus

logger = logging.getLogger(__name__)

# Delay before attempt n+1, indexed by the number of attempts already made.
BACKOFF_SECONDS = [30, 120, 600, 1800, 3600]
# A row stuck in "sending" this long belongs to a worker that died.
STALE_SENDING_AFTER = timedelta(minutes=10)


def queue_email(
    *,
    kind: str,
    to: str,
    subject: str,
    body: str,
    idempotency_key: str,
    business=None,
    user=None,
    entity=None,
    contains_secret: bool = False,
) -> Notification:
    """Write an outbox row and schedule delivery after the surrounding transaction commits.

    Calling this twice with the same ``idempotency_key`` returns the existing row
    and sends nothing new.
    """
    notification, created = Notification.objects.get_or_create(
        idempotency_key=idempotency_key[:200],
        defaults={
            "kind": kind,
            "recipient_email": to,
            "recipient_user": user,
            "subject": subject[:200],
            "body": body,
            "business": business,
            "contains_secret": contains_secret,
            "max_attempts": settings.NOTIFICATION_MAX_ATTEMPTS,
            "entity_type": entity._meta.label_lower if entity is not None else "",
            "entity_id": str(entity.pk) if entity is not None else "",
        },
    )
    if created:
        transaction.on_commit(lambda: enqueue_delivery(notification.pk))
    return notification


def enqueue_delivery(notification_id: int) -> None:
    from .tasks import deliver_notification

    try:
        deliver_notification.delay(notification_id)
    except Exception as exc:  # broker down: the outbox relay will deliver it later
        logger.warning(
            "notification_enqueue_failed",
            extra={"notification_id": notification_id, "error": type(exc).__name__},
        )


def retry(notification: Notification) -> Notification:
    """Manually re-queue a failed notification with a fresh attempt budget."""
    from apps.core.exceptions import ConflictError

    with transaction.atomic():
        locked = Notification.objects.select_for_update().get(pk=notification.pk)
        if locked.status not in (NotificationStatus.FAILED, NotificationStatus.CANCELLED):
            raise ConflictError(
                "Only failed or cancelled notifications can be retried.",
                code="notification_not_retryable",
            )
        if locked.contains_secret and not locked.body:
            raise ConflictError(
                "This message contained a one-time link and cannot be resent.",
                code="notification_not_retryable",
            )
        locked.status = NotificationStatus.PENDING
        locked.attempts = 0
        locked.next_attempt_at = timezone.now()
        locked.last_error = ""
        locked.save(
            update_fields=["status", "attempts", "next_attempt_at", "last_error", "updated_at"]
        )
        transaction.on_commit(lambda: enqueue_delivery(locked.pk))
    return locked


def claim(notification_id: int) -> Notification | None:
    """Lock a due notification and mark it as sending. Returns None if not deliverable now."""
    now = timezone.now()
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(skip_locked=True)
            .filter(pk=notification_id, status=NotificationStatus.PENDING, next_attempt_at__lte=now)
            .first()
        )
        if notification is None:
            return None
        notification.status = NotificationStatus.SENDING
        notification.attempts += 1
        notification.locked_at = now
        notification.save(update_fields=["status", "attempts", "locked_at", "updated_at"])
    return notification


def mark_sent(notification: Notification) -> None:
    notification.status = NotificationStatus.SENT
    notification.sent_at = timezone.now()
    notification.last_error = ""
    fields = ["status", "sent_at", "last_error", "updated_at"]
    if notification.contains_secret:
        notification.body = ""
        fields.append("body")
    notification.save(update_fields=fields)


def mark_failed_attempt(notification: Notification, error: Exception) -> None:
    notification.last_error = f"{type(error).__name__}: {error}"[:500]
    if notification.attempts >= notification.max_attempts:
        notification.status = NotificationStatus.FAILED
    else:
        delay = BACKOFF_SECONDS[min(notification.attempts - 1, len(BACKOFF_SECONDS) - 1)]
        notification.status = NotificationStatus.PENDING
        notification.next_attempt_at = timezone.now() + timedelta(seconds=delay)
    notification.save(update_fields=["status", "last_error", "next_attempt_at", "updated_at"])


def due_notification_ids(limit: int = 200) -> list[int]:
    """Ids the relay should hand to workers: due pending rows and rows stuck in sending."""
    now = timezone.now()
    Notification.objects.filter(
        status=NotificationStatus.SENDING, locked_at__lt=now - STALE_SENDING_AFTER
    ).update(status=NotificationStatus.PENDING, next_attempt_at=now)
    return list(
        Notification.objects.filter(status=NotificationStatus.PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )
