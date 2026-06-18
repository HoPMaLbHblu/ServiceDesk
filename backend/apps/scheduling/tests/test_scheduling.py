from datetime import timedelta

import pytest

from apps.core.exceptions import ConflictError
from apps.core.tests.concurrency import run_concurrently
from apps.scheduling import services as scheduling
from apps.scheduling.models import Appointment, AppointmentStatus, TechnicianAvailability, TimeOff

pytestmark = pytest.mark.django_db


def book(shop, starts_at, minutes=60, technician=None):
    return scheduling.book(
        business=shop.business,
        customer=shop.customer,
        technician=technician or shop.technician,
        starts_at=starts_at,
        duration_minutes=minutes,
        actor=shop.manager,
    )


def test_overlapping_appointment_is_refused_with_details(shop, next_weekday_10am):
    first = book(shop, next_weekday_10am)
    with pytest.raises(ConflictError) as exc:
        book(shop, next_weekday_10am + timedelta(minutes=30))
    assert exc.value.error_code == "appointment_conflict"
    assert exc.value.details["conflicting_appointment"] == str(first.public_id)
    # Back-to-back is fine, and another technician can take the same slot.
    book(shop, next_weekday_10am + timedelta(minutes=60))
    book(shop, next_weekday_10am, technician=shop.manager)


def test_cancelled_appointments_free_the_slot(shop, next_weekday_10am):
    first = book(shop, next_weekday_10am)
    scheduling.set_status(appointment=first, status=AppointmentStatus.CANCELLED, actor=shop.manager)
    book(shop, next_weekday_10am)


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrent_booking_of_the_same_slot(shop, next_weekday_10am):
    results = run_concurrently(
        lambda offset: book(shop, next_weekday_10am + timedelta(minutes=offset)),
        [(i * 10,) for i in range(5)],
    )
    booked = [r for r in results if isinstance(r, Appointment)]
    conflicts = [
        r
        for r in results
        if isinstance(r, ConflictError) and r.error_code == "appointment_conflict"
    ]
    assert len(booked) == 1 and len(conflicts) == 4, results
    assert Appointment.objects.filter(technician=shop.technician, status="scheduled").count() == 1


def test_business_hours_and_timezone(shop, next_weekday_10am):
    with pytest.raises(ConflictError) as exc:
        book(shop, next_weekday_10am.replace(hour=7))
    assert exc.value.error_code == "outside_business_hours"
    with pytest.raises(ConflictError):
        book(shop, next_weekday_10am.replace(hour=17, minute=30))  # would end after 18:00
    sunday = next_weekday_10am + timedelta(days=(6 - next_weekday_10am.weekday()))
    with pytest.raises(ConflictError):
        book(shop, sunday)
    appointment = book(shop, next_weekday_10am)
    # Stored in UTC, displayed by clients in the business timezone.
    assert (
        appointment.starts_at.utcoffset() == timedelta(0)
        or appointment.starts_at.tzinfo is not None
    )


def test_technician_availability_and_time_off(shop, next_weekday_10am):
    TechnicianAvailability.objects.create(
        business=shop.business,
        technician=shop.technician,
        weekday=next_weekday_10am.weekday(),
        start_time=next_weekday_10am.replace(hour=12).time(),
        end_time=next_weekday_10am.replace(hour=16).time(),
    )
    with pytest.raises(ConflictError) as exc:
        book(shop, next_weekday_10am)
    assert exc.value.error_code == "technician_unavailable"
    noon = next_weekday_10am.replace(hour=12)
    TimeOff.objects.create(
        business=shop.business,
        technician=shop.technician,
        starts_at=noon,
        ends_at=noon + timedelta(hours=1),
    )
    with pytest.raises(ConflictError):
        book(shop, noon)
    book(shop, noon + timedelta(hours=1))


def test_reschedule_checks_conflicts(shop, next_weekday_10am):
    first = book(shop, next_weekday_10am)
    second = book(shop, next_weekday_10am + timedelta(hours=2))
    client = shop.client("manager")
    response = client.post(
        f"/api/v1/appointments/{second.public_id}/reschedule/",
        {"starts_at": first.starts_at.isoformat(), "duration_minutes": 60},
    )
    assert response.status_code == 409 and response.data["error"]["code"] == "appointment_conflict"
    new_time = next_weekday_10am + timedelta(hours=4)
    response = client.post(
        f"/api/v1/appointments/{second.public_id}/reschedule/",
        {"starts_at": new_time.isoformat(), "duration_minutes": 30},
    )
    assert response.status_code == 200


def test_free_slots_exclude_booked_time(shop, next_weekday_10am):
    book(shop, next_weekday_10am)
    response = shop.client("manager").get(
        "/api/v1/appointments/availability/",
        {
            "technician": str(shop.technician.public_id),
            "date": next_weekday_10am.date().isoformat(),
            "duration_minutes": 60,
        },
    )
    starts = [s[11:16] for s in response.data]
    assert (
        "09:00" in starts and "10:00" not in starts and "10:30" not in starts and "11:00" in starts
    )


def test_reminders_are_queued_once(shop):
    from django.utils import timezone

    from apps.notifications.models import Notification, NotificationKind

    appointment = Appointment.objects.create(
        business=shop.business,
        customer=shop.customer,
        technician=shop.technician,
        starts_at=timezone.now() + timedelta(hours=3),
        ends_at=timezone.now() + timedelta(hours=4),
    )
    assert scheduling.queue_due_reminders() == 1
    assert scheduling.queue_due_reminders() == 0
    assert (
        Notification.objects.filter(
            kind=NotificationKind.APPOINTMENT_REMINDER, entity_id=str(appointment.pk)
        ).count()
        == 1
    )
