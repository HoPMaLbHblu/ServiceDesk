from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.accounts.tokens import hash_token, new_opaque_token
from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError
from apps.core.money import compute_totals, line_total
from apps.orders import services as orders
from apps.orders.models import EventKind, OrderStatus

from .models import ApprovalLink, DecisionChannel, Estimate, EstimateLine, EstimateStatus, LineKind

DRAFTABLE_ORDER_STATUSES = {
    OrderStatus.DIAGNOSING,
    OrderStatus.AWAITING_APPROVAL,
    OrderStatus.IN_PROGRESS,
}


def _lock(estimate: Estimate) -> Estimate:
    return (
        Estimate.objects.select_for_update().select_related("order", "business").get(pk=estimate.pk)
    )


@transaction.atomic
def create_version(*, order, actor) -> Estimate:
    """Start a new draft. Lines are copied from the previous version so a revision starts from it.

    A version that was sent but not decided is superseded at once, so its
    approval link stops working.
    """
    order = orders.lock(order)
    orders.ensure_not_terminal(order)
    if order.status not in DRAFTABLE_ORDER_STATUSES:
        raise ConflictError(
            "Start diagnosing the device before preparing an estimate.", code="invalid_state"
        )
    if Estimate.objects.filter(order=order, status=EstimateStatus.DRAFT).exists():
        raise ConflictError("This order already has a draft estimate.", code="draft_exists")

    previous = Estimate.objects.select_for_update().filter(order=order).order_by("-version").first()
    if previous and previous.status == EstimateStatus.SENT:
        previous.status = EstimateStatus.SUPERSEDED
        previous.save(update_fields=["status", "updated_at"])
        ApprovalLink.objects.filter(estimate=previous, used_at__isnull=True).update(
            expires_at=timezone.now()
        )

    business = order.business
    version = (Estimate.objects.filter(order=order).aggregate(v=Max("version"))["v"] or 0) + 1
    estimate = Estimate.objects.create(
        business=business,
        order=order,
        version=version,
        currency=business.currency,
        tax_rate=business.tax_rate,
        notes=previous.notes if previous else "",
        created_by=actor,
    )
    if previous:
        for line in previous.lines.all():
            EstimateLine.objects.create(
                business=business,
                estimate=estimate,
                position=line.position,
                kind=line.kind,
                part=line.part,
                sku=line.sku,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                taxable=line.taxable,
                line_total=line.line_total,
            )
        _recalculate(estimate)
    orders.add_event(
        order, kind=EventKind.ESTIMATE, actor=actor, message=f"Estimate version {version} drafted."
    )
    return estimate


def _recalculate(estimate: Estimate) -> None:
    totals = compute_totals(
        ((line.line_total, line.taxable) for line in estimate.lines.all()), estimate.tax_rate
    )
    estimate.subtotal, estimate.tax_total, estimate.total = (
        totals.subtotal,
        totals.tax_total,
        totals.total,
    )
    estimate.save(update_fields=["subtotal", "tax_total", "total", "updated_at"])


@transaction.atomic
def replace_lines(*, estimate: Estimate, lines: list[dict], notes: str | None, actor) -> Estimate:
    """Replace a draft's lines. Catalog parts are copied into the line (description, SKU, price)."""
    estimate = _lock(estimate)
    if estimate.status != EstimateStatus.DRAFT:
        raise ConflictError(
            "Only draft estimates can be edited. Create a new version to change a sent estimate.",
            code="estimate_locked",
        )
    estimate.lines.all().delete()
    for position, data in enumerate(lines):
        part = data.get("part")
        if part is not None and part.business_id != estimate.business_id:
            raise DomainError("Unknown part.", code="cross_tenant_reference")
        description = (data.get("description") or (part.name if part else "")).strip()
        if not description:
            raise DomainError(
                "Each line needs a description.",
                fields={f"lines.{position}.description": ["Required."]},
            )
        unit_price = data.get("unit_price")
        if unit_price is None:
            unit_price = part.selling_price if part else Decimal("0.00")
        quantity = Decimal(data["quantity"])
        EstimateLine.objects.create(
            business_id=estimate.business_id,
            estimate=estimate,
            position=position,
            kind=data.get("kind") or (LineKind.PART if part else LineKind.LABOR),
            part=part,
            sku=part.sku if part else "",
            description=description[:255],
            quantity=quantity,
            unit_price=unit_price,
            taxable=data.get("taxable", True),
            line_total=line_total(quantity, unit_price),
        )
    if notes is not None:
        estimate.notes = notes
        estimate.save(update_fields=["notes", "updated_at"])
    _recalculate(estimate)
    return estimate


def content_hash(estimate: Estimate) -> str:
    payload = {
        "version": estimate.version,
        "currency": estimate.currency,
        "tax_rate": str(estimate.tax_rate),
        "notes": estimate.notes,
        "subtotal": str(estimate.subtotal),
        "tax_total": str(estimate.tax_total),
        "total": str(estimate.total),
        "lines": [
            [
                line.kind,
                line.sku,
                line.description,
                str(line.quantity),
                str(line.unit_price),
                line.taxable,
                str(line.line_total),
            ]
            for line in estimate.lines.order_by("position", "id")
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@transaction.atomic
def send(*, estimate: Estimate, actor) -> tuple[Estimate, str]:
    """Freeze a draft, email the customer an approval link, and move the order to awaiting approval."""
    estimate = _lock(estimate)
    order = orders.lock(estimate.order)
    orders.ensure_not_terminal(order)
    if estimate.status != EstimateStatus.DRAFT:
        raise ConflictError("This estimate was already sent.", code="estimate_locked")
    if not estimate.lines.exists():
        raise DomainError("Add at least one line before sending.", code="estimate_empty")

    # An approved earlier version stops applying once a new version is sent.
    Estimate.objects.filter(order=order, status=EstimateStatus.APPROVED).update(
        status=EstimateStatus.SUPERSEDED
    )

    business = estimate.business
    today = timezone.now().astimezone(business.tzinfo).date()
    estimate.status = EstimateStatus.SENT
    estimate.sent_at = timezone.now()
    estimate.valid_until = today + timedelta(days=business.estimate_valid_days)
    estimate.content_hash = content_hash(estimate)
    estimate.save(update_fields=["status", "sent_at", "valid_until", "content_hash", "updated_at"])

    raw, digest = new_opaque_token()
    ApprovalLink.objects.create(
        estimate=estimate,
        token_hash=digest,
        expires_at=timezone.now() + settings.ESTIMATE_APPROVAL_LINK_MAX_AGE,
    )
    orders.add_event(
        order,
        kind=EventKind.ESTIMATE,
        actor=actor,
        message=f"Estimate version {estimate.version} sent for approval ({estimate.currency} {estimate.total}).",
        visible_to_customer=True,
        data={"estimate_id": str(estimate.public_id), "version": estimate.version},
    )
    if order.status in (OrderStatus.DIAGNOSING, OrderStatus.IN_PROGRESS):
        orders.transition(
            order=order, to_status=OrderStatus.AWAITING_APPROVAL, actor=actor, system=True
        )
    _email_approval_request(estimate, raw)
    record(
        action="estimate.sent",
        entity=estimate,
        actor=actor,
        changes={"version": estimate.version, "total": estimate.total},
        label=str(estimate),
    )
    return estimate, raw


def _email_approval_request(estimate: Estimate, raw_token: str) -> None:
    from apps.notifications.emails import footer, link
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    customer = estimate.order.customer
    if not customer.email:
        return
    business = estimate.business
    queue_email(
        kind=NotificationKind.ESTIMATE_APPROVAL_REQUEST,
        to=customer.email,
        business=business,
        subject=f"Estimate for {estimate.order.reference}: {estimate.currency} {estimate.total}",
        body=(
            f"Hello {customer.full_name},\n\nWe prepared an estimate for the repair of your {estimate.order.device}.\n\n"
            f"Total: {estimate.currency} {estimate.total} (including {estimate.currency} {estimate.tax_total} tax)\n"
            f"Valid until: {estimate.valid_until:%B %d, %Y}\n\n"
            f"Review and approve or decline it here:\n{link(f'/approve/{raw_token}')}\n\n"
            "Nothing is charged until you approve." + footer(business)
        ),
        idempotency_key=f"estimate-approval:{estimate.pk}",
        contains_secret=True,
        entity=estimate,
    )


def _is_expired(estimate: Estimate) -> bool:
    today = timezone.now().astimezone(estimate.business.tzinfo).date()
    return estimate.valid_until is not None and estimate.valid_until < today


@transaction.atomic
def decide(
    *,
    estimate: Estimate,
    approve: bool,
    channel: str,
    decided_by=None,
    decided_by_name: str = "",
    note: str = "",
    expected_hash: str | None = None,
) -> Estimate:
    """Approve or reject exactly this estimate version.

    The decision is refused if the version is not the one currently awaiting a
    decision, has expired, or its content differs from what the customer saw.
    """
    estimate = _lock(estimate)
    order = orders.lock(estimate.order)
    if estimate.status != EstimateStatus.SENT:
        raise ConflictError(
            f"This estimate is {estimate.get_status_display().lower()} and can no longer be decided.",
            code="estimate_not_pending",
            details={"status": estimate.status},
        )
    latest_version = Estimate.objects.filter(order=order).aggregate(v=Max("version"))["v"]
    if estimate.version != latest_version:
        raise ConflictError("A newer version of this estimate exists.", code="estimate_superseded")
    if _is_expired(estimate):
        raise ConflictError(
            "This estimate has expired. Ask the shop for a new one.", code="estimate_expired"
        )
    if expected_hash is not None and expected_hash != estimate.content_hash:
        raise ConflictError(
            "The estimate changed since you opened it. Reload and review it again.",
            code="estimate_changed",
        )
    if content_hash(estimate) != estimate.content_hash:
        raise ConflictError(
            "The estimate content does not match what was sent.", code="estimate_changed"
        )

    estimate.status = EstimateStatus.APPROVED if approve else EstimateStatus.REJECTED
    estimate.decided_at = timezone.now()
    estimate.decided_by = decided_by if getattr(decided_by, "is_authenticated", False) else None
    estimate.decided_by_name = (
        decided_by_name or (decided_by.full_name if estimate.decided_by else "")
    )[:200]
    estimate.decision_channel = channel
    estimate.decision_note = note
    estimate.save()
    ApprovalLink.objects.filter(estimate=estimate, used_at__isnull=True).update(
        used_at=timezone.now()
    )

    verb = "approved" if approve else "declined"
    via = {
        DecisionChannel.PORTAL: "in the customer portal",
        DecisionChannel.LINK: "using the approval link",
        DecisionChannel.STAFF: f"(recorded by {decided_by.full_name if decided_by else 'staff'})",
    }[channel]
    orders.add_event(
        order,
        kind=EventKind.ESTIMATE,
        actor=estimate.decided_by,
        message=f"Estimate version {estimate.version} {verb} by {estimate.decided_by_name or 'the customer'} {via}."
        + (f" Note: {note}" if note else ""),
        visible_to_customer=True,
        data={
            "estimate_id": str(estimate.public_id),
            "version": estimate.version,
            "decision": verb,
        },
    )
    record(
        action=f"estimate.{'approved' if approve else 'rejected'}",
        entity=estimate,
        business=estimate.business,
        actor=decided_by,
        changes={
            "version": estimate.version,
            "total": estimate.total,
            "content_hash": estimate.content_hash,
            "channel": channel,
            "name": estimate.decided_by_name,
        },
        label=str(estimate),
    )
    if approve and order.status == OrderStatus.AWAITING_APPROVAL:
        orders.transition(
            order=order, to_status=OrderStatus.IN_PROGRESS, actor=estimate.decided_by, system=True
        )
    return estimate


def find_link(raw_token: str) -> ApprovalLink | None:
    return (
        ApprovalLink.objects.select_related(
            "estimate__order__customer", "estimate__order__device", "estimate__business"
        )
        .filter(token_hash=hash_token(raw_token))
        .first()
    )


def link_state(approval_link: ApprovalLink) -> str:
    """``open``, ``used`` or ``expired`` for the public approval page."""
    if approval_link.used_at:
        return "used"
    if approval_link.expires_at <= timezone.now():
        return "expired"
    return "open"
