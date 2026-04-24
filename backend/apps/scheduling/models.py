from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func, Q

from apps.core.models import PublicIdModel, TenantModel


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = models.DateTimeField()  # only used inside the exclusion constraint


class BusinessHours(TenantModel):
    """Opening hours for one weekday (0 = Monday) in the business timezone."""

    weekday = models.PositiveSmallIntegerField()
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "weekday"], name="business_hours_unique_weekday"
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6), name="business_hours_weekday_range"
            ),
            models.CheckConstraint(
                condition=Q(is_closed=True)
                | Q(
                    opens_at__isnull=False,
                    closes_at__isnull=False,
                    closes_at__gt=models.F("opens_at"),
                ),
                name="business_hours_open_range_valid",
            ),
        ]


class TechnicianAvailability(TenantModel):
    """Weekly working window for a technician (business timezone)."""

    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["technician", "weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=models.F("start_time")), name="availability_range_valid"
            ),
            models.CheckConstraint(
                condition=Q(weekday__gte=0, weekday__lte=6), name="availability_weekday_range"
            ),
        ]


class TimeOff(TenantModel):
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="time_off_range_valid"
            ),
        ]


class AppointmentStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    NO_SHOW = "no_show", "No-show"


class AppointmentKind(models.TextChoices):
    DROP_OFF = "drop_off", "Device drop-off"
    DIAGNOSIS = "diagnosis", "Diagnosis"
    REPAIR = "repair", "Repair"
    PICKUP = "pickup", "Pickup"


class Appointment(PublicIdModel, TenantModel):
    order = models.ForeignKey(
        "orders.RepairOrder",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="appointments"
    )
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments"
    )
    kind = models.CharField(
        max_length=20, choices=AppointmentKind.choices, default=AppointmentKind.DIAGNOSIS
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=AppointmentStatus.choices, default=AppointmentStatus.SCHEDULED
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    reminder_queued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["business", "starts_at"]),
            models.Index(fields=["technician", "starts_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="appointment_range_valid"
            ),
            # The database itself refuses two active appointments for one
            # technician whose time ranges overlap, even under concurrent requests.
            ExclusionConstraint(
                name="appointment_no_technician_overlap",
                expressions=[
                    ("technician", RangeOperators.EQUAL),
                    (TsTzRange("starts_at", "ends_at", RangeBoundary()), RangeOperators.OVERLAPS),
                ],
                condition=Q(status="scheduled"),
            ),
        ]
