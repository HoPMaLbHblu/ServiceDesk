from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError
from apps.orders import services as orders
from apps.orders.models import EventKind, OrderStatus

from .models import Appointment, AppointmentStatus, BusinessHours, TechnicianAvailability, TimeOff

MIN_DURATION = 15
MAX_DURATION = 8 * 60
SLOT_STEP = timedelta(minutes=15)


def _local(dt: datetime, business) -> datetime:
    return dt.astimezone(business.tzinfo)


def _window_ok(start_local: datetime, end_local: datetime, opens: time, closes: time) -> bool:
    return (
        start_local.date() == end_local.date()
        and opens <= start_local.time()
        and end_local.time() <= closes
    )


def check_availability(
    *, business, technician, starts_at: datetime, ends_at: datetime, exclude_id: int | None = None
) -> None:
    """Validate opening hours, technician hours and time off.

    Overlap with other appointments is enforced by the database exclusion
    constraint when the row is written; this function gives friendlier errors first.
    """
    if ends_at <= starts_at:
        raise DomainError(
            "The appointment must end after it starts.",
            fields={"duration_minutes": ["Invalid duration."]},
        )
    start_local, end_local = _local(starts_at, business), _local(ends_at, business)
    hours = BusinessHours.objects.filter(business=business, weekday=start_local.weekday()).first()
    if hours is None or hours.is_closed:
        raise ConflictError(
            f"The shop is closed on {start_local:%A}s.", code="outside_business_hours"
        )
    if not _window_ok(start_local, end_local, hours.opens_at, hours.closes_at):
        raise ConflictError(
            f"Appointments on {start_local:%A} must fall between {hours.opens_at:%H:%M} and {hours.closes_at:%H:%M} "
            f"({business.timezone}).",
            code="outside_business_hours",
        )
    windows = TechnicianAvailability.objects.filter(business=business, technician=technician)
    if windows.exists():
        today = windows.filter(weekday=start_local.weekday())
        if not any(_window_ok(start_local, end_local, w.start_time, w.end_time) for w in today):
            raise ConflictError(
                f"{technician.full_name} is not working at that time.",
                code="technician_unavailable",
            )
    if TimeOff.objects.filter(
        business=business, technician=technician, starts_at__lt=ends_at, ends_at__gt=starts_at
    ).exists():
        raise ConflictError(
            f"{technician.full_name} is off at that time.", code="technician_unavailable"
        )


def _conflict(business, technician, starts_at, ends_at, exclude_id=None) -> ConflictError:
    clash = (
        Appointment.objects.filter(
            business=business,
            technician=technician,
            status=AppointmentStatus.SCHEDULED,
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
        .exclude(pk=exclude_id)
        .first()
    )
    details = {}
    if clash is not None:
        details = {
            "conflicting_appointment": str(clash.public_id),
            "starts_at": clash.starts_at.isoformat(),
            "ends_at": clash.ends_at.isoformat(),
        }
    return ConflictError(
        f"{technician.full_name} already has an appointment at that time.",
        code="appointment_conflict",
        details=details,
    )


def _save_guarded(appointment: Appointment, business, **save_kwargs) -> None:
    try:
        with transaction.atomic():
            appointment.save(**save_kwargs)
    except IntegrityError as exc:
        if "appointment_no_technician_overlap" in str(exc):
            raise _conflict(
                business,
                appointment.technician,
                appointment.starts_at,
                appointment.ends_at,
                appointment.pk,
            ) from exc
        raise


@transaction.atomic
def book(
    *,
    business,
    customer,
    technician,
    starts_at: datetime,
    duration_minutes: int,
    actor,
    kind: str = "diagnosis",
    order=None,
    notes: str = "",
) -> Appointment:
    if customer.business_id != business.pk or (
        order is not None and order.business_id != business.pk
    ):
        raise DomainError("Unknown customer or order.", code="cross_tenant_reference")
    if order is not None and order.customer_id != customer.pk:
        raise DomainError(
            "The order belongs to a different customer.",
            fields={"order": ["Choose this customer's order."]},
        )
    orders.ensure_technician(business, technician)
    if not MIN_DURATION <= duration_minutes <= MAX_DURATION:
        raise DomainError(
            f"Duration must be between {MIN_DURATION} and {MAX_DURATION} minutes.",
            fields={"duration_minutes": ["Out of range."]},
        )
    if starts_at < timezone.now() - timedelta(minutes=5):
        raise DomainError(
            "Appointments cannot start in the past.",
            fields={"starts_at": ["Choose a future time."]},
        )
    if order is not None:
        order = orders.lock(order)
        orders.ensure_not_terminal(order)
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    check_availability(
        business=business, technician=technician, starts_at=starts_at, ends_at=ends_at
    )

    appointment = Appointment(
        business=business,
        order=order,
        customer=customer,
        technician=technician,
        kind=kind,
        starts_at=starts_at,
        ends_at=ends_at,
        notes=notes,
        created_by=actor,
    )
    _save_guarded(appointment, business)

    if order is not None:
        if order.assigned_technician_id is None:
            order.assigned_technician = technician
            order.version += 1
            order.save(update_fields=["assigned_technician", "version", "updated_at"])
        orders.add_event(
            order,
            kind=EventKind.APPOINTMENT,
            actor=actor,
            message=f"{appointment.get_kind_display()} booked for {_local(starts_at, business):%a %d %b %Y, %H:%M}.",
            visible_to_customer=True,
        )
        if order.status == OrderStatus.NEW:
            orders.transition(
                order=order, to_status=OrderStatus.SCHEDULED, actor=actor, system=True
            )
    record(
        action="appointment.booked",
        entity=appointment,
        actor=actor,
        changes={"technician": technician.email, "starts_at": starts_at, "ends_at": ends_at},
        label=f"{customer.full_name} {starts_at:%Y-%m-%d %H:%M}",
    )
    _email_confirmation(appointment, rescheduled=False)
    return appointment


@transaction.atomic
def reschedule(
    *, appointment: Appointment, starts_at: datetime, duration_minutes: int, actor, technician=None
) -> Appointment:
    appointment = (
        Appointment.objects.select_for_update()
        .select_related("business", "customer", "technician")
        .get(pk=appointment.pk)
    )
    if appointment.status != AppointmentStatus.SCHEDULED:
        raise ConflictError(
            "Only scheduled appointments can be rescheduled.", code="appointment_not_scheduled"
        )
    business = appointment.business
    technician = technician or appointment.technician
    orders.ensure_technician(business, technician)
    if starts_at < timezone.now() - timedelta(minutes=5):
        raise DomainError(
            "Appointments cannot start in the past.",
            fields={"starts_at": ["Choose a future time."]},
        )
    ends_at = starts_at + timedelta(minutes=duration_minutes)
    check_availability(
        business=business,
        technician=technician,
        starts_at=starts_at,
        ends_at=ends_at,
        exclude_id=appointment.pk,
    )
    old = (appointment.starts_at, appointment.technician.email)
    appointment.starts_at, appointment.ends_at, appointment.technician = (
        starts_at,
        ends_at,
        technician,
    )
    appointment.reminder_queued_at = None
    _save_guarded(appointment, business)
    if appointment.order_id:
        orders.add_event(
            appointment.order,
            kind=EventKind.APPOINTMENT,
            actor=actor,
            message=f"Appointment moved to {_local(starts_at, business):%a %d %b %Y, %H:%M}.",
            visible_to_customer=True,
        )
    record(
        action="appointment.rescheduled",
        entity=appointment,
        actor=actor,
        changes={"starts_at": [old[0], starts_at], "technician": [old[1], technician.email]},
    )
    _email_confirmation(appointment, rescheduled=True)
    return appointment


@transaction.atomic
def set_status(*, appointment: Appointment, status: str, actor, reason: str = "") -> Appointment:
    appointment = (
        Appointment.objects.select_for_update().select_related("business").get(pk=appointment.pk)
    )
    if appointment.status != AppointmentStatus.SCHEDULED:
        raise ConflictError("This appointment is already closed.", code="appointment_not_scheduled")
    if status not in (
        AppointmentStatus.CANCELLED,
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW,
    ):
        raise DomainError("Unknown status.")
    appointment.status = status
    if status == AppointmentStatus.CANCELLED:
        appointment.cancelled_at = timezone.now()
        appointment.cancellation_reason = reason[:255]
    appointment.save()
    order = appointment.order
    if order is not None and status == AppointmentStatus.CANCELLED:
        orders.add_event(
            order,
            kind=EventKind.APPOINTMENT,
            actor=actor,
            message="Appointment cancelled." + (f" {reason}" if reason else ""),
            visible_to_customer=True,
        )
        still_booked = Appointment.objects.filter(
            order=order, status=AppointmentStatus.SCHEDULED
        ).exists()
        if order.status == OrderStatus.SCHEDULED and not still_booked:
            orders.transition(order=order, to_status=OrderStatus.NEW, actor=actor, system=True)
    record(
        action=f"appointment.{status}",
        entity=appointment,
        actor=actor,
        changes={"reason": reason} if reason else {},
    )
    return appointment


def free_slots(*, business, technician, day: date, duration_minutes: int) -> list[datetime]:
    """Start times on ``day`` (business timezone) where a booking would currently succeed."""
    tz = business.tzinfo
    hours = BusinessHours.objects.filter(business=business, weekday=day.weekday()).first()
    if hours is None or hours.is_closed:
        return []
    duration = timedelta(minutes=duration_minutes)
    cursor = datetime.combine(day, hours.opens_at, tzinfo=tz)
    close = datetime.combine(day, hours.closes_at, tzinfo=tz)
    busy = list(
        Appointment.objects.filter(
            business=business,
            technician=technician,
            status=AppointmentStatus.SCHEDULED,
            starts_at__lt=close,
            ends_at__gt=cursor,
        ).values_list("starts_at", "ends_at")
    )
    now = timezone.now()
    slots = []
    while cursor + duration <= close:
        end = cursor + duration
        if cursor >= now and not any(s < end and e > cursor for s, e in busy):
            try:
                check_availability(
                    business=business, technician=technician, starts_at=cursor, ends_at=end
                )
                slots.append(cursor)
            except (ConflictError, DomainError):
                pass
        cursor += SLOT_STEP
    return slots


def _email_confirmation(appointment: Appointment, *, rescheduled: bool) -> None:
    from apps.notifications.emails import footer
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    customer = appointment.customer
    if not customer.email:
        return
    business = appointment.business
    local = _local(appointment.starts_at, business)
    queue_email(
        kind=NotificationKind.APPOINTMENT_CONFIRMATION,
        to=customer.email,
        business=business,
        subject=f"{'Rescheduled' if rescheduled else 'Confirmed'}: appointment on {local:%a %d %b} at {local:%H:%M}",
        body=(
            f"Hello {customer.full_name},\n\nYour {appointment.get_kind_display().lower()} appointment with {business.name} "
            f"is {'now ' if rescheduled else ''}booked for {local:%A %d %B %Y at %H:%M} ({business.timezone}).\n"
            + (f"\nAddress: {business.address}\n" if business.address else "")
            + (f"Phone: {business.phone}\n" if business.phone else "")
            + footer(business)
        ),
        idempotency_key=f"appointment:{appointment.pk}:{appointment.starts_at.isoformat()}:{appointment.technician_id}",
        entity=appointment,
    )


def queue_due_reminders(now: datetime | None = None) -> int:
    """Queue one reminder per appointment starting in the next 24 hours."""
    from apps.notifications.emails import footer
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    now = now or timezone.now()
    count = 0
    due = Appointment.objects.filter(
        status=AppointmentStatus.SCHEDULED,
        reminder_queued_at__isnull=True,
        starts_at__gt=now,
        starts_at__lte=now + timedelta(hours=24),
        business__is_active=True,
    ).values_list("pk", flat=True)
    for appointment_id in due:
        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update(skip_locked=True)
                .select_related("business", "customer")
                .filter(
                    pk=appointment_id,
                    reminder_queued_at__isnull=True,
                    status=AppointmentStatus.SCHEDULED,
                )
                .first()
            )
            if appointment is None:
                continue
            appointment.reminder_queued_at = now
            appointment.save(update_fields=["reminder_queued_at", "updated_at"])
            customer = appointment.customer
            if customer.email:
                local = _local(appointment.starts_at, appointment.business)
                queue_email(
                    kind=NotificationKind.APPOINTMENT_REMINDER,
                    to=customer.email,
                    business=appointment.business,
                    subject=f"Reminder: appointment on {local:%a %d %b} at {local:%H:%M}",
                    body=(
                        f"Hello {customer.full_name},\n\nThis is a reminder of your appointment with "
                        f"{appointment.business.name} on {local:%A %d %B at %H:%M}."
                        + footer(appointment.business)
                    ),
                    idempotency_key=f"appointment-reminder:{appointment.pk}:{appointment.starts_at.isoformat()}",
                    entity=appointment,
                )
                count += 1
    return count
