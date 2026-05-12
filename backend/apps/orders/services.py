from __future__ import annotations

import hashlib

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.businesses.models import Membership, Role
from apps.core.exceptions import ConflictError, DomainError, InvalidTransition

from . import workflow
from .models import Attachment, EventKind, OrderEvent, OrderSource, OrderStatus, RepairOrder

EDITABLE_FIELDS = [
    "problem_description",
    "priority",
    "expected_completion_date",
    "assigned_technician",
]


def add_event(
    order: RepairOrder,
    *,
    kind: str,
    actor=None,
    message: str = "",
    visible_to_customer: bool = False,
    **extra,
) -> OrderEvent:
    actor_label = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        actor_label = actor.full_name
    else:
        actor = None
    return OrderEvent.objects.create(
        business_id=order.business_id,
        order=order,
        kind=kind,
        actor=actor,
        actor_label=actor_label or "System",
        message=message,
        visible_to_customer=visible_to_customer,
        from_status=extra.pop("from_status", ""),
        to_status=extra.pop("to_status", ""),
        data=extra.pop("data", {}),
    )


def ensure_technician(business, user) -> None:
    """Assigned technicians must be active staff of the same business."""
    if user is None:
        return
    is_staff = Membership.objects.filter(
        business=business,
        user=user,
        is_active=True,
        role__in=[Role.OWNER, Role.MANAGER, Role.TECHNICIAN],
    ).exists()
    if not is_staff:
        raise DomainError(
            "The selected technician is not an active member of this workspace.",
            code="invalid_technician",
            fields={"assigned_technician": ["Choose an active team member."]},
        )


def lock(order: RepairOrder) -> RepairOrder:
    return RepairOrder.objects.select_for_update().get(pk=order.pk, business_id=order.business_id)


def ensure_not_terminal(order: RepairOrder) -> None:
    if order.is_terminal:
        raise ConflictError(
            f"{order.reference} is {order.get_status_display().lower()} and can no longer be changed.",
            code="order_closed",
        )


@transaction.atomic
def create_order(
    *,
    business,
    customer,
    device,
    problem_description: str,
    actor,
    priority: str = "normal",
    assigned_technician=None,
    expected_completion_date=None,
    source: str = OrderSource.STAFF,
) -> RepairOrder:
    from apps.billing.services import assert_order_limit
    from apps.businesses.services import next_number

    if customer.business_id != business.pk or device.business_id != business.pk:
        raise DomainError(
            "Customer and device must belong to this workspace.", code="cross_tenant_reference"
        )
    if device.customer_id != customer.pk:
        raise DomainError(
            "This device belongs to a different customer.",
            code="device_customer_mismatch",
            fields={"device": ["Choose one of this customer's devices."]},
        )
    ensure_technician(business, assigned_technician)
    assert_order_limit(business)

    order = RepairOrder.objects.create(
        business=business,
        number=next_number(business, "repair_order"),
        customer=customer,
        device=device,
        problem_description=problem_description,
        priority=priority,
        assigned_technician=assigned_technician,
        expected_completion_date=expected_completion_date,
        source=source,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        status_changed_at=timezone.now(),
    )
    add_event(
        order,
        kind=EventKind.CREATED,
        actor=actor,
        message=workflow.CUSTOMER_MESSAGES[OrderStatus.NEW],
        visible_to_customer=True,
        to_status=OrderStatus.NEW,
    )
    if assigned_technician:
        add_event(
            order,
            kind=EventKind.ASSIGNED,
            actor=actor,
            message=f"Assigned to {assigned_technician.full_name}.",
        )
    record(
        action="order.created",
        entity=order,
        actor=actor,
        changes={"source": source},
        label=order.reference,
    )
    return order


@transaction.atomic
def update_order(
    *, order: RepairOrder, actor, data: dict, expected_version: int | None
) -> RepairOrder:
    order = lock(order)
    ensure_not_terminal(order)
    if expected_version is not None and expected_version != order.version:
        raise ConflictError(
            "Someone else changed this order. Reload to see the latest version.",
            code="stale_version",
            details={"current_version": order.version},
        )
    changes = {}
    for field in EDITABLE_FIELDS:
        if field in data and getattr(order, field) != data[field]:
            changes[field] = data[field]
    if not changes:
        return order
    if "assigned_technician" in changes:
        ensure_technician(order.business, changes["assigned_technician"])
    before = {field: getattr(order, field) for field in changes}
    for field, value in changes.items():
        setattr(order, field, value)
    order.version += 1
    order.save()

    if "assigned_technician" in changes:
        technician = changes["assigned_technician"]
        add_event(
            order,
            kind=EventKind.ASSIGNED,
            actor=actor,
            message=f"Assigned to {technician.full_name}."
            if technician
            else "Technician unassigned.",
        )
    other = [f for f in changes if f != "assigned_technician"]
    if other:
        add_event(
            order,
            kind=EventKind.UPDATED,
            actor=actor,
            message="Updated " + ", ".join(f.replace("_", " ") for f in other) + ".",
        )
    record(
        action="order.updated",
        entity=order,
        actor=actor,
        changes={f: [_plain(before[f]), _plain(changes[f])] for f in changes},
        label=order.reference,
    )
    return order


def _plain(value):
    if hasattr(value, "email"):
        return value.email
    return value


def _check_guards(order: RepairOrder, target: str, reason: str) -> None:
    from apps.estimates.models import Estimate, EstimateStatus
    from apps.inventory.models import PartReservation, ReservationStatus
    from apps.invoicing.models import Invoice, InvoiceStatus
    from apps.scheduling.models import Appointment, AppointmentStatus

    latest = Estimate.objects.filter(order=order).order_by("-version").first()
    if (
        target == OrderStatus.SCHEDULED
        and not Appointment.objects.filter(order=order, status=AppointmentStatus.SCHEDULED).exists()
    ):
        raise InvalidTransition(
            "Book an appointment to schedule this order.", code="appointment_required"
        )
    if target == OrderStatus.DIAGNOSING and order.assigned_technician_id is None:
        raise InvalidTransition(
            "Assign a technician before starting diagnosis.", code="technician_required"
        )
    if target == OrderStatus.AWAITING_APPROVAL and (
        latest is None or latest.status != EstimateStatus.SENT
    ):
        raise InvalidTransition("Send an estimate to the customer first.", code="estimate_not_sent")
    if target == OrderStatus.IN_PROGRESS and order.status == OrderStatus.AWAITING_APPROVAL:
        if latest is None or latest.status != EstimateStatus.APPROVED:
            raise InvalidTransition(
                "The latest estimate has not been approved.", code="estimate_not_approved"
            )
    if target == OrderStatus.READY_FOR_PICKUP:
        if PartReservation.objects.filter(order=order, status=ReservationStatus.ACTIVE).exists():
            raise InvalidTransition(
                "Consume or release the parts reserved for this order first.",
                code="reservations_open",
            )
    if (
        target == OrderStatus.COMPLETED
        and not Invoice.objects.filter(order=order, status=InvoiceStatus.ISSUED).exists()
    ):
        raise InvalidTransition(
            "Issue an invoice before completing the order.", code="invoice_required"
        )
    if target == OrderStatus.CANCELLED:
        if not reason.strip():
            raise DomainError(
                "Give a reason for cancelling.",
                code="reason_required",
                fields={"reason": ["Required."]},
            )
        if Invoice.objects.filter(order=order, status=InvoiceStatus.ISSUED).exists():
            raise InvalidTransition(
                "Void the issued invoice before cancelling this order.", code="invoice_issued"
            )


@transaction.atomic
def transition(
    *,
    order: RepairOrder,
    to_status: str,
    actor,
    tenant=None,
    reason: str = "",
    system: bool = False,
) -> RepairOrder:
    """Move an order to ``to_status`` after checking the state machine and its guards.

    ``tenant`` is the acting staff member's context (role checks). ``system`` is
    set by other workflow steps (sending an estimate, booking an appointment).
    """
    order = lock(order)
    current = order.status
    if to_status == current:
        return order
    if not workflow.can_transition(current, to_status):
        raise InvalidTransition(
            f"An order that is {order.get_status_display().lower()} cannot move to "
            f"{OrderStatus(to_status).label.lower()}.",
            details={
                "from": current,
                "to": to_status,
                "allowed": sorted(workflow.TRANSITIONS.get(current, set())),
            },
        )
    if not system:
        if (current, to_status) in workflow.SYSTEM_ONLY:
            raise InvalidTransition(
                "This status is set automatically by another step.", code="system_transition"
            )
        if tenant is not None and tenant.is_technician:
            if (
                order.assigned_technician_id != actor.pk
                or (current, to_status) not in workflow.TECHNICIAN_TRANSITIONS
            ):
                raise InvalidTransition(
                    "Your role does not allow this status change.", code="transition_forbidden"
                )
    _check_guards(order, to_status, reason)

    now = timezone.now()
    order.status = to_status
    order.status_changed_at = now
    order.version += 1
    if to_status == OrderStatus.COMPLETED:
        order.completed_at = now
    if to_status == OrderStatus.CANCELLED:
        order.cancelled_at = now
        order.cancellation_reason = reason.strip()
        _release_on_cancel(order, actor)
    order.save()

    message = workflow.CUSTOMER_MESSAGES[to_status]
    if to_status == OrderStatus.CANCELLED:
        message = f"{message} Reason: {order.cancellation_reason}"
    add_event(
        order,
        kind=EventKind.STATUS_CHANGED,
        actor=actor,
        message=message,
        visible_to_customer=True,
        from_status=current,
        to_status=to_status,
    )
    record(
        action="order.status_changed",
        entity=order,
        actor=actor,
        changes={
            "status": [current, to_status],
            **({"reason": order.cancellation_reason} if reason else {}),
        },
        label=order.reference,
    )
    if to_status in workflow.CUSTOMER_NOTIFIED:
        notify_customer_of_status(order)
    return order


def _release_on_cancel(order: RepairOrder, actor) -> None:
    from apps.inventory import services as inventory
    from apps.inventory.models import PartReservation, ReservationStatus
    from apps.scheduling.models import Appointment, AppointmentStatus

    for reservation in PartReservation.objects.filter(order=order, status=ReservationStatus.ACTIVE):
        inventory.release(reservation=reservation, actor=actor, reason="Order cancelled")
    Appointment.objects.filter(order=order, status=AppointmentStatus.SCHEDULED).update(
        status=AppointmentStatus.CANCELLED,
        cancelled_at=timezone.now(),
        cancellation_reason="Order cancelled",
    )


def notify_customer_of_status(order: RepairOrder) -> None:
    from apps.notifications.emails import footer, link
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    customer = order.customer
    if not customer.email:
        return
    business = order.business
    queue_email(
        kind=NotificationKind.ORDER_STATUS,
        to=customer.email,
        business=business,
        subject=f"{order.reference}: {order.get_status_display()}",
        body=(
            f"Hello {customer.full_name},\n\n{workflow.CUSTOMER_MESSAGES[order.status]}\n\n"
            f"Order: {order.reference}\nDevice: {order.device}\n"
            + (
                f"\nYou can follow the repair in the customer portal: {link('/portal')}\n"
                if customer.portal_access.filter(revoked_at__isnull=True).exists()
                else ""
            )
            + footer(business)
        ),
        idempotency_key=f"order-status:{order.pk}:{order.status}:{order.version}",
        entity=order,
    )


@transaction.atomic
def record_diagnostics(*, order: RepairOrder, findings: str, actor) -> RepairOrder:
    order = lock(order)
    if order.status not in (
        OrderStatus.DIAGNOSING,
        OrderStatus.AWAITING_APPROVAL,
        OrderStatus.IN_PROGRESS,
    ):
        raise ConflictError(
            "Diagnostics can be recorded while diagnosing or repairing.", code="invalid_state"
        )
    order.diagnostic_findings = findings.strip()
    order.diagnosed_at = timezone.now()
    order.diagnosed_by = actor
    order.version += 1
    order.save()
    add_event(order, kind=EventKind.DIAGNOSTICS, actor=actor, message=order.diagnostic_findings)
    record(action="order.diagnostics_recorded", entity=order, actor=actor, label=order.reference)
    return order


@transaction.atomic
def add_note(*, order: RepairOrder, body: str, visible_to_customer: bool, actor) -> OrderEvent:
    body = body.strip()
    if not body:
        raise DomainError("Write a note first.", fields={"body": ["Required."]})
    kind = EventKind.CUSTOMER_UPDATE if visible_to_customer else EventKind.INTERNAL_NOTE
    return add_event(
        order, kind=kind, actor=actor, message=body, visible_to_customer=visible_to_customer
    )


# --- Attachments ---------------------------------------------------------------

# Allowed types are detected from the file's first bytes, never from the name or
# the browser-supplied content type.
SIGNATURES = [
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
    (b"%PDF-", "application/pdf", "pdf"),
]


def sniff(head: bytes) -> tuple[str, str] | None:
    for signature, content_type, ext in SIGNATURES:
        if head.startswith(signature):
            return content_type, ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


@transaction.atomic
def add_attachment(
    *, order: RepairOrder, upload, actor, visible_to_customer: bool, caption: str = ""
) -> Attachment:
    from django.conf import settings

    if upload.size > settings.MAX_UPLOAD_SIZE:
        raise DomainError(
            f"Files can be at most {settings.MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
            code="file_too_large",
            fields={"file": ["File is too large."]},
        )
    if upload.size == 0:
        raise DomainError(
            "The file is empty.", code="file_empty", fields={"file": ["File is empty."]}
        )
    head = upload.read(16)
    upload.seek(0)
    detected = sniff(head)
    if detected is None:
        raise DomainError(
            "Only JPEG, PNG, GIF, WebP images and PDF documents can be attached.",
            code="file_type_not_allowed",
            fields={"file": ["Unsupported file type."]},
        )
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    original = (upload.name or "file").replace("/", "_").replace("\\", "_")[:200]
    attachment = Attachment(
        business_id=order.business_id,
        order=order,
        uploaded_by=actor,
        original_name=original,
        content_type=detected[0],
        size=upload.size,
        sha256=digest.hexdigest(),
        visible_to_customer=visible_to_customer,
        caption=caption[:200],
    )
    attachment.file.save(f"{digest.hexdigest()[:12]}.{detected[1]}", upload, save=False)
    attachment.save()
    add_event(
        order,
        kind=EventKind.ATTACHMENT,
        actor=actor,
        message=f"Attached {original}.",
        visible_to_customer=visible_to_customer,
        data={"attachment_id": str(attachment.public_id)},
    )
    return attachment
