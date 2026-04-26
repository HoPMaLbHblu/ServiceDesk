import logging

from celery import shared_task
from django.core.mail import EmailMessage

from . import services

logger = logging.getLogger(__name__)


def send(notification) -> None:
    EmailMessage(
        subject=notification.subject,
        body=notification.body,
        to=[notification.recipient_email],
        headers={"X-ServiceDesk-Notification": str(notification.pk)},
    ).send(fail_silently=False)


@shared_task(ignore_result=True)
def deliver_notification(notification_id: int) -> str:
    """Deliver one outbox row. Safe to call any number of times for the same id."""
    notification = services.claim(notification_id)
    if notification is None:
        return "skipped"
    try:
        send(notification)
    except Exception as exc:  # SMTP and network errors are recorded and retried with backoff
        services.mark_failed_attempt(notification, exc)
        logger.warning(
            "notification_delivery_failed",
            extra={
                "notification_id": notification.pk,
                "attempt": notification.attempts,
                "error": type(exc).__name__,
            },
        )
        return "failed"
    services.mark_sent(notification)
    return "sent"


@shared_task(ignore_result=True)
def relay_outbox() -> int:
    """Periodic sweep that re-dispatches due rows the broker never delivered."""
    ids = services.due_notification_ids()
    for notification_id in ids:
        services.enqueue_delivery(notification_id)
    return len(ids)
