from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from apps.notifications import services, tasks
from apps.notifications.models import Notification, NotificationStatus

pytestmark = pytest.mark.django_db


def queue(key="k1", **extra):
    return services.queue_email(
        kind="order_status",
        to="c@example.com",
        subject="Hi",
        body="Body",
        idempotency_key=key,
        **extra,
    )


def test_same_event_queues_one_email():
    first = queue()
    second = queue()
    assert first.pk == second.pk and Notification.objects.count() == 1


def test_delivery_sends_once_even_if_task_runs_twice():
    notification = queue()
    assert tasks.deliver_notification(notification.pk) == "sent"
    assert tasks.deliver_notification(notification.pk) == "skipped"
    assert len(mail.outbox) == 1
    notification.refresh_from_db()
    assert notification.status == NotificationStatus.SENT and notification.attempts == 1


def test_failures_retry_with_backoff_then_stop(settings):
    notification = queue()
    with mock.patch.object(tasks, "send", side_effect=ConnectionRefusedError("smtp down")):
        assert tasks.deliver_notification(notification.pk) == "failed"
        notification.refresh_from_db()
        assert notification.status == NotificationStatus.PENDING
        assert notification.next_attempt_at > timezone.now() + timedelta(seconds=20)
        assert "smtp down" in notification.last_error
        # Not due yet: a duplicate task does nothing.
        assert tasks.deliver_notification(notification.pk) == "skipped"
        for _ in range(notification.max_attempts - 1):
            Notification.objects.filter(pk=notification.pk).update(next_attempt_at=timezone.now())
            tasks.deliver_notification(notification.pk)
    notification.refresh_from_db()
    assert notification.status == NotificationStatus.FAILED
    assert notification.attempts == notification.max_attempts
    assert len(mail.outbox) == 0


def test_manual_retry_of_failed_notification(shop):
    notification = queue(business=shop.business)
    Notification.objects.filter(pk=notification.pk).update(
        status=NotificationStatus.FAILED, attempts=5
    )
    client = shop.client("manager")
    response = client.post(f"/api/v1/notifications/{notification.pk}/retry/")
    assert (
        response.status_code == 200
        and response.data["status"] == "pending"
        and response.data["attempts"] == 0
    )
    assert tasks.deliver_notification(notification.pk) == "sent"
    response = client.post(f"/api/v1/notifications/{notification.pk}/retry/")
    assert response.status_code == 409


def test_relay_recovers_stuck_and_lost_rows():
    lost = queue("lost")
    stuck = queue("stuck")
    Notification.objects.filter(pk=stuck.pk).update(
        status=NotificationStatus.SENDING, locked_at=timezone.now() - timedelta(minutes=30)
    )
    with mock.patch.object(services, "enqueue_delivery") as enqueue:
        assert tasks.relay_outbox() == 2
    assert {c.args[0] for c in enqueue.call_args_list} == {lost.pk, stuck.pk}


def test_broker_outage_does_not_break_the_request():
    with mock.patch.object(
        tasks.deliver_notification, "delay", side_effect=ConnectionError("redis down")
    ):
        services.enqueue_delivery(123)  # logged, not raised


def test_one_time_link_bodies_are_hidden_in_the_api(shop):
    services.queue_email(
        kind="invitation",
        to="x@example.com",
        subject="Join",
        body="secret link",
        idempotency_key="sec",
        business=shop.business,
        contains_secret=True,
    )
    rows = shop.client("owner").get("/api/v1/notifications/").data["results"]
    assert rows[0]["body"].startswith("[Contains a one-time link")
