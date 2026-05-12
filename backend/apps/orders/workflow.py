"""Repair order state machine.

Every status change goes through :func:`apps.orders.services.transition`, which
checks the table and guards below on the server. The table is also exposed to
the interface (``allowed_transitions``) so buttons match what the API accepts.
"""

from .models import OrderStatus as S

TRANSITIONS: dict[str, set[str]] = {
    S.NEW: {S.SCHEDULED, S.DIAGNOSING, S.CANCELLED},
    S.SCHEDULED: {S.NEW, S.DIAGNOSING, S.CANCELLED},
    S.DIAGNOSING: {S.AWAITING_APPROVAL, S.CANCELLED},
    # Rejected estimate: back to diagnosing to revise the quote.
    S.AWAITING_APPROVAL: {S.IN_PROGRESS, S.DIAGNOSING, S.CANCELLED},
    # Extra work found during the repair needs a new estimate version.
    S.IN_PROGRESS: {S.AWAITING_APPROVAL, S.READY_FOR_PICKUP, S.CANCELLED},
    # Rework after a failed final check.
    S.READY_FOR_PICKUP: {S.COMPLETED, S.IN_PROGRESS, S.CANCELLED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

# Transitions a technician may perform on orders assigned to them.
TECHNICIAN_TRANSITIONS: set[tuple[str, str]] = {
    (S.NEW, S.DIAGNOSING),
    (S.SCHEDULED, S.DIAGNOSING),
    (S.IN_PROGRESS, S.READY_FOR_PICKUP),
    (S.READY_FOR_PICKUP, S.IN_PROGRESS),
}

# Transitions only reachable through another workflow step, not the generic endpoint.
SYSTEM_ONLY: set[tuple[str, str]] = {
    (S.DIAGNOSING, S.AWAITING_APPROVAL),  # sending an estimate
    (S.IN_PROGRESS, S.AWAITING_APPROVAL),  # sending a revised estimate
    (S.NEW, S.SCHEDULED),  # booking an appointment
    (S.SCHEDULED, S.NEW),  # cancelling the last appointment
}

# Status changes the customer is emailed about. Estimate requests have their own email.
CUSTOMER_NOTIFIED = {S.DIAGNOSING, S.IN_PROGRESS, S.READY_FOR_PICKUP, S.COMPLETED, S.CANCELLED}

CUSTOMER_MESSAGES = {
    S.NEW: "We received your repair request.",
    S.SCHEDULED: "Your appointment is booked.",
    S.DIAGNOSING: "A technician is diagnosing your device.",
    S.AWAITING_APPROVAL: "An estimate is waiting for your approval.",
    S.IN_PROGRESS: "The repair is in progress.",
    S.READY_FOR_PICKUP: "Your device is ready for pickup.",
    S.COMPLETED: "The repair is complete and the device was handed back.",
    S.CANCELLED: "The repair order was cancelled.",
}


def can_transition(from_status: str, to_status: str) -> bool:
    return to_status in TRANSITIONS.get(from_status, set())


def allowed_for(order, tenant, user) -> list[str]:
    """Targets the given user may request from the generic transition endpoint."""
    targets = []
    for target in TRANSITIONS.get(order.status, set()):
        if (order.status, target) in SYSTEM_ONLY:
            continue
        if tenant.is_technician:
            if (
                order.assigned_technician_id != user.pk
                or (order.status, target) not in TECHNICIAN_TRANSITIONS
            ):
                continue
        targets.append(target)
    order_index = list(S.values)
    return sorted(targets, key=order_index.index)
