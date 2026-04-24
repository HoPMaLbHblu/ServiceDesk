import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import PublicIdModel, TenantModel


class OrderStatus(models.TextChoices):
    NEW = "new", "New"
    SCHEDULED = "scheduled", "Scheduled"
    DIAGNOSING = "diagnosing", "Diagnosing"
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
    IN_PROGRESS = "in_progress", "In progress"
    READY_FOR_PICKUP = "ready_for_pickup", "Ready for pickup"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


TERMINAL_STATUSES = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED})


class PaymentStatus(models.TextChoices):
    NOT_INVOICED = "not_invoiced", "Not invoiced"
    UNPAID = "unpaid", "Unpaid"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    PAID = "paid", "Paid"
    REFUNDED = "refunded", "Refunded"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent"


class OrderSource(models.TextChoices):
    STAFF = "staff", "Created by staff"
    PORTAL = "portal", "Customer request"


class RepairOrder(PublicIdModel, TenantModel):
    number = models.PositiveIntegerField()
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    device = models.ForeignKey("customers.Device", on_delete=models.PROTECT, related_name="orders")
    problem_description = models.TextField()
    status = models.CharField(
        max_length=24, choices=OrderStatus.choices, default=OrderStatus.NEW, db_index=True
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.NOT_INVOICED,
        db_index=True,
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    source = models.CharField(max_length=10, choices=OrderSource.choices, default=OrderSource.STAFF)
    assigned_technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_orders",
    )
    expected_completion_date = models.DateField(null=True, blank=True)
    diagnostic_findings = models.TextField(blank=True)
    diagnosed_at = models.DateTimeField(null=True, blank=True)
    diagnosed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status_changed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Optimistic concurrency token for edits made from two screens at once.
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "number"], name="order_number_unique_per_business"
            ),
            models.CheckConstraint(
                condition=~Q(status="completed") | Q(completed_at__isnull=False),
                name="order_completed_has_timestamp",
            ),
            models.CheckConstraint(
                condition=~Q(status="cancelled") | Q(cancelled_at__isnull=False),
                name="order_cancelled_has_timestamp",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "status"]),
            models.Index(fields=["business", "assigned_technician", "status"]),
            models.Index(fields=["business", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.reference

    @property
    def reference(self) -> str:
        return f"RO-{self.number:05d}"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


class EventKind(models.TextChoices):
    CREATED = "created", "Order created"
    STATUS_CHANGED = "status_changed", "Status changed"
    ASSIGNED = "assigned", "Technician assigned"
    UPDATED = "updated", "Details updated"
    DIAGNOSTICS = "diagnostics", "Diagnostics recorded"
    INTERNAL_NOTE = "internal_note", "Internal note"
    CUSTOMER_UPDATE = "customer_update", "Customer update"
    ATTACHMENT = "attachment", "Attachment added"
    ESTIMATE = "estimate", "Estimate"
    PARTS = "parts", "Parts"
    APPOINTMENT = "appointment", "Appointment"
    INVOICE = "invoice", "Invoice"
    PAYMENT = "payment", "Payment"


class OrderEvent(TenantModel):
    """Immutable timeline entry. Updates and deletes are blocked in the database."""

    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=EventKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_label = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    visible_to_customer = models.BooleanField(default=False)
    from_status = models.CharField(max_length=24, blank=True)
    to_status = models.CharField(max_length=24, blank=True)
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["order", "created_at"])]


def attachment_path(instance, filename: str) -> str:
    # The stored name is random; the original filename is kept in the database only.
    return f"attachments/{instance.business_id}/{instance.order_id}/{uuid.uuid4().hex}"


class Attachment(PublicIdModel, TenantModel):
    order = models.ForeignKey(RepairOrder, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    file = models.FileField(upload_to=attachment_path, max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    visible_to_customer = models.BooleanField(default=False)
    caption = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
