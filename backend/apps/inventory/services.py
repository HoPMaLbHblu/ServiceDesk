"""Every stock change goes through these functions.

Each function locks the part row (``SELECT ... FOR UPDATE``) before reading
quantities, writes an immutable StockMovement, and relies on CHECK constraints
as a final guard, so concurrent requests can never oversell or go negative.
Reserve and consume accept an idempotency key: repeating a request returns the
first result instead of changing stock twice.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError
from apps.orders.models import EventKind, OrderStatus

from .models import MovementKind, Part, PartReservation, ReservationStatus, StockMovement

RESERVABLE_ORDER_STATUSES = {
    OrderStatus.DIAGNOSING,
    OrderStatus.AWAITING_APPROVAL,
    OrderStatus.IN_PROGRESS,
}


def _lock_part(part: Part) -> Part:
    return Part.objects.select_for_update().get(pk=part.pk, business_id=part.business_id)


def _movement(
    part: Part,
    *,
    kind: str,
    on_hand_delta=Decimal("0"),
    reserved_delta=Decimal("0"),
    actor=None,
    **extra,
) -> StockMovement:
    part.quantity_on_hand += on_hand_delta
    part.quantity_reserved += reserved_delta
    if part.quantity_on_hand < 0:
        raise ConflictError(
            f"Only {part.quantity_on_hand - on_hand_delta} {part.get_unit_display().lower()}(s) of {part.name} on hand.",
            code="insufficient_stock",
        )
    part.save(update_fields=["quantity_on_hand", "quantity_reserved", "updated_at"])
    movement = StockMovement.objects.create(
        business_id=part.business_id,
        part=part,
        kind=kind,
        on_hand_delta=on_hand_delta,
        reserved_delta=reserved_delta,
        on_hand_after=part.quantity_on_hand,
        reserved_after=part.quantity_reserved,
        unit_cost=part.purchase_cost,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        **extra,
    )
    _maybe_alert_low_stock(part, movement)
    return movement


def _maybe_alert_low_stock(part: Part, movement: StockMovement) -> None:
    """Alert owners and managers when available stock drops to or below the threshold."""
    if part.low_stock_threshold <= 0:
        return
    available_after = part.quantity_available
    available_before = available_after - (movement.on_hand_delta - movement.reserved_delta)
    if not (available_after <= part.low_stock_threshold < available_before):
        return
    from apps.businesses.models import Membership, Role
    from apps.notifications.emails import footer, link
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    recipients = Membership.objects.select_related("user").filter(
        business_id=part.business_id, is_active=True, role__in=[Role.OWNER, Role.MANAGER]
    )
    for membership in recipients:
        queue_email(
            kind=NotificationKind.LOW_STOCK,
            to=membership.user.email,
            user=membership.user,
            business=part.business,
            subject=f"Low stock: {part.name} ({part.sku})",
            body=(
                f"{part.name} ({part.sku}) is low: {available_after} available, threshold {part.low_stock_threshold}.\n\n"
                f"Review inventory: {link('/inventory?low_stock=true')}" + footer(part.business)
            ),
            idempotency_key=f"low-stock:{movement.pk}:{membership.user_id}",
            entity=part,
        )


@transaction.atomic
def receive_stock(
    *, part: Part, quantity: Decimal, actor, reason: str = "", unit_cost: Decimal | None = None
) -> StockMovement:
    if quantity <= 0:
        raise DomainError("Quantity must be positive.", fields={"quantity": ["Must be positive."]})
    part = _lock_part(part)
    if unit_cost is not None and unit_cost != part.purchase_cost:
        part.purchase_cost = unit_cost
    movement = _movement(
        part,
        kind=MovementKind.RECEIPT,
        on_hand_delta=quantity,
        actor=actor,
        reason=reason or "Stock received",
    )
    record(
        action="inventory.received",
        entity=part,
        actor=actor,
        changes={"quantity": quantity, "on_hand": part.quantity_on_hand},
        label=part.sku,
    )
    return movement


@transaction.atomic
def adjust_stock(*, part: Part, counted_quantity: Decimal, actor, reason: str) -> StockMovement:
    """Set on-hand stock to a physical count. The difference is recorded with a reason."""
    if not reason.strip():
        raise DomainError("Explain why stock is being adjusted.", fields={"reason": ["Required."]})
    if counted_quantity < 0:
        raise DomainError(
            "The count cannot be negative.", fields={"counted_quantity": ["Cannot be negative."]}
        )
    part = _lock_part(part)
    if counted_quantity < part.quantity_reserved:
        raise ConflictError(
            f"{part.quantity_reserved} are reserved for orders. Release reservations before counting lower.",
            code="below_reserved",
            details={"reserved": str(part.quantity_reserved)},
        )
    delta = counted_quantity - part.quantity_on_hand
    if delta == 0:
        raise DomainError("The count matches current stock; nothing to adjust.", code="no_change")
    movement = _movement(
        part, kind=MovementKind.ADJUSTMENT, on_hand_delta=delta, actor=actor, reason=reason.strip()
    )
    record(
        action="inventory.adjusted",
        entity=part,
        actor=actor,
        changes={
            "on_hand": [str(counted_quantity - delta), str(counted_quantity)],
            "reason": reason.strip(),
        },
        label=part.sku,
    )
    return movement


@transaction.atomic
def reserve(
    *, order, part: Part, quantity: Decimal, actor, idempotency_key: str
) -> tuple[PartReservation, bool]:
    """Reserve stock for an order. Returns ``(reservation, created)``."""
    from apps.orders import services as orders

    if not idempotency_key:
        raise DomainError("An idempotency key is required.", code="idempotency_key_required")
    existing = PartReservation.objects.filter(
        business_id=order.business_id, idempotency_key=idempotency_key
    ).first()
    if existing:
        if (
            existing.order_id != order.pk
            or existing.part_id != part.pk
            or existing.quantity != quantity
        ):
            raise ConflictError(
                "This request key was already used for a different reservation.",
                code="idempotency_conflict",
            )
        return existing, False
    if part.business_id != order.business_id:
        raise DomainError("Unknown part.", code="cross_tenant_reference")
    if quantity <= 0:
        raise DomainError("Quantity must be positive.", fields={"quantity": ["Must be positive."]})

    order = orders.lock(order)
    if order.status not in RESERVABLE_ORDER_STATUSES:
        raise ConflictError(
            "Parts can be reserved while the order is being diagnosed or repaired.",
            code="invalid_state",
        )
    part = _lock_part(part)
    # Re-check under the order lock: a concurrent duplicate may have committed meanwhile.
    existing = PartReservation.objects.filter(
        business_id=order.business_id, idempotency_key=idempotency_key
    ).first()
    if existing:
        return existing, False
    if not part.is_active:
        raise ConflictError(f"{part.name} is archived.", code="part_inactive")
    if part.quantity_available < quantity:
        raise ConflictError(
            f"Only {part.quantity_available} of {part.name} available.",
            code="insufficient_stock",
            details={
                "part": str(part.public_id),
                "available": str(part.quantity_available),
                "requested": str(quantity),
            },
        )
    reservation = PartReservation.objects.create(
        business_id=order.business_id,
        order=order,
        part=part,
        quantity=quantity,
        idempotency_key=idempotency_key,
        created_by=actor,
    )
    _movement(
        part,
        kind=MovementKind.RESERVATION,
        reserved_delta=quantity,
        actor=actor,
        order=order,
        reservation=reservation,
        reason=f"Reserved for {order.reference}",
        idempotency_key=f"reserve:{idempotency_key}",
    )
    orders.add_event(
        order,
        kind=EventKind.PARTS,
        actor=actor,
        message=f"Reserved {quantity} × {part.name} ({part.sku}).",
    )
    return reservation, True


def _lock_reservation(reservation: PartReservation) -> PartReservation:
    return (
        PartReservation.objects.select_for_update()
        .select_related("part", "order")
        .get(pk=reservation.pk)
    )


@transaction.atomic
def consume(*, reservation: PartReservation, actor) -> tuple[PartReservation, bool]:
    """Use reserved parts in the repair. Consuming an already consumed reservation is a no-op."""
    from apps.orders import services as orders

    reservation = _lock_reservation(reservation)
    if reservation.status == ReservationStatus.CONSUMED:
        return reservation, False
    if reservation.status != ReservationStatus.ACTIVE:
        raise ConflictError(
            "This reservation was released and cannot be consumed.", code="reservation_released"
        )
    order = orders.lock(reservation.order)
    if order.status not in RESERVABLE_ORDER_STATUSES:
        raise ConflictError(
            "Parts can be used while the order is being diagnosed or repaired.",
            code="invalid_state",
        )
    part = _lock_part(reservation.part)
    _movement(
        part,
        kind=MovementKind.CONSUMPTION,
        on_hand_delta=-reservation.quantity,
        reserved_delta=-reservation.quantity,
        actor=actor,
        order=order,
        reservation=reservation,
        reason=f"Used in {order.reference}",
        idempotency_key=f"consume:{reservation.pk}",
    )
    reservation.status = ReservationStatus.CONSUMED
    reservation.consumed_at = timezone.now()
    reservation.save(update_fields=["status", "consumed_at", "updated_at"])
    orders.add_event(
        order,
        kind=EventKind.PARTS,
        actor=actor,
        message=f"Used {reservation.quantity} × {part.name} ({part.sku}).",
    )
    record(
        action="inventory.consumed",
        entity=part,
        actor=actor,
        changes={"quantity": reservation.quantity, "order": order.reference},
        label=part.sku,
    )
    return reservation, True


@transaction.atomic
def release(
    *, reservation: PartReservation, actor, reason: str = ""
) -> tuple[PartReservation, bool]:
    """Return reserved parts to available stock. Releasing twice is a no-op."""
    from apps.orders import services as orders

    reservation = _lock_reservation(reservation)
    if reservation.status == ReservationStatus.RELEASED:
        return reservation, False
    if reservation.status != ReservationStatus.ACTIVE:
        raise ConflictError("Consumed parts cannot be released.", code="reservation_consumed")
    part = _lock_part(reservation.part)
    _movement(
        part,
        kind=MovementKind.RELEASE,
        reserved_delta=-reservation.quantity,
        actor=actor,
        order=reservation.order,
        reservation=reservation,
        reason=reason or f"Released from {reservation.order.reference}",
        idempotency_key=f"release:{reservation.pk}",
    )
    reservation.status = ReservationStatus.RELEASED
    reservation.released_at = timezone.now()
    reservation.save(update_fields=["status", "released_at", "updated_at"])
    orders.add_event(
        reservation.order,
        kind=EventKind.PARTS,
        actor=actor,
        message=f"Released {reservation.quantity} × {part.name} ({part.sku}).",
    )
    return reservation, True
