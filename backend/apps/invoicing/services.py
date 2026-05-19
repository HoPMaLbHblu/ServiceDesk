from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError
from apps.core.money import ZERO, quantize
from apps.estimates.models import Estimate, EstimateStatus
from apps.orders import services as orders
from apps.orders.models import EventKind, OrderStatus, PaymentStatus

from .models import Invoice, InvoiceLine, InvoiceStatus, Payment, PaymentKind

INVOICEABLE_STATUSES = {OrderStatus.IN_PROGRESS, OrderStatus.READY_FOR_PICKUP}
DEFAULT_DUE_DAYS = 14


def _lock_invoice(invoice: Invoice) -> Invoice:
    return (
        Invoice.objects.select_for_update().select_related("order", "business").get(pk=invoice.pk)
    )


def payment_status_for(invoice: Invoice) -> str:
    if invoice.status == InvoiceStatus.VOID:
        return PaymentStatus.NOT_INVOICED
    if invoice.amount_paid >= invoice.total:
        return PaymentStatus.PAID
    if invoice.amount_paid == ZERO:
        has_refunds = invoice.payments.filter(kind=PaymentKind.REFUND).exists()
        return PaymentStatus.REFUNDED if has_refunds else PaymentStatus.UNPAID
    return PaymentStatus.PARTIALLY_PAID


def _sync_order_payment_status(invoice: Invoice) -> None:
    order = invoice.order
    new_status = payment_status_for(invoice)
    if order.payment_status != new_status:
        order.payment_status = new_status
        order.save(update_fields=["payment_status", "updated_at"])


@transaction.atomic
def issue_invoice(*, order, actor, due_days: int = DEFAULT_DUE_DAYS, notes: str = "") -> Invoice:
    """Issue an invoice from the approved estimate. Lines and party details are copied, so later
    catalog, price or customer changes never alter an issued invoice."""
    from apps.businesses.services import next_number

    order = orders.lock(order)
    orders.ensure_not_terminal(order)
    if order.status not in INVOICEABLE_STATUSES:
        raise ConflictError(
            "Invoices are issued once the repair is under way or ready for pickup.",
            code="invalid_state",
        )
    if Invoice.objects.filter(order=order, status=InvoiceStatus.ISSUED).exists():
        raise ConflictError("This order already has an issued invoice.", code="invoice_exists")
    estimate = Estimate.objects.filter(order=order).order_by("-version").first()
    if estimate is None or estimate.status != EstimateStatus.APPROVED:
        raise ConflictError(
            "The latest estimate must be approved before invoicing.", code="estimate_not_approved"
        )

    business = order.business
    customer = order.customer
    now = timezone.now()
    invoice = Invoice.objects.create(
        business=business,
        order=order,
        estimate=estimate,
        number=next_number(business, "invoice"),
        currency=estimate.currency,
        tax_rate=estimate.tax_rate,
        subtotal=estimate.subtotal,
        tax_total=estimate.tax_total,
        total=estimate.total,
        issued_at=now,
        due_date=now.astimezone(business.tzinfo).date() + timedelta(days=due_days),
        issued_by=actor,
        notes=notes,
        business_snapshot={
            "name": business.name,
            "email": business.email,
            "phone": business.phone,
            "address": business.address,
        },
        customer_snapshot={
            "name": customer.full_name,
            "company": customer.company,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
        },
    )
    for line in estimate.lines.all():
        InvoiceLine.objects.create(
            business=business,
            invoice=invoice,
            position=line.position,
            kind=line.kind,
            sku=line.sku,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            taxable=line.taxable,
            line_total=line.line_total,
        )
    _sync_order_payment_status(invoice)
    orders.add_event(
        order,
        kind=EventKind.INVOICE,
        actor=actor,
        message=f"Invoice {invoice.reference} issued for {invoice.currency} {invoice.total}.",
        visible_to_customer=True,
        data={"invoice_id": str(invoice.public_id)},
    )
    record(
        action="invoice.issued",
        entity=invoice,
        actor=actor,
        changes={"number": invoice.number, "total": invoice.total},
        label=invoice.reference,
    )
    return invoice


@transaction.atomic
def void_invoice(*, invoice: Invoice, reason: str, actor) -> Invoice:
    invoice = _lock_invoice(invoice)
    if invoice.status != InvoiceStatus.ISSUED:
        raise ConflictError("This invoice is already void.", code="invoice_void")
    if invoice.order.is_terminal:
        raise ConflictError("Invoices of closed orders cannot be voided.", code="order_closed")
    if invoice.amount_paid > ZERO:
        raise ConflictError(
            "Refund the recorded payments before voiding this invoice.", code="invoice_has_payments"
        )
    if not reason.strip():
        raise DomainError("Give a reason for voiding.", fields={"reason": ["Required."]})
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = timezone.now()
    invoice.void_reason = reason.strip()
    invoice.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
    _sync_order_payment_status(invoice)
    orders.add_event(
        invoice.order,
        kind=EventKind.INVOICE,
        actor=actor,
        message=f"Invoice {invoice.reference} voided: {invoice.void_reason}",
    )
    record(
        action="invoice.voided",
        entity=invoice,
        actor=actor,
        changes={"reason": invoice.void_reason},
        label=invoice.reference,
    )
    return invoice


def _existing_by_key(
    business, key: str, *, invoice: Invoice, kind: str, amount: Decimal
) -> Payment | None:
    if not key:
        return None
    existing = Payment.objects.filter(business=business, idempotency_key=key).first()
    if existing is None:
        return None
    if existing.invoice_id != invoice.pk or existing.kind != kind or existing.amount != amount:
        raise ConflictError(
            "This request key was already used for a different payment.",
            code="idempotency_conflict",
        )
    return existing


@transaction.atomic
def record_payment(
    *,
    invoice: Invoice,
    amount: Decimal,
    method: str,
    actor,
    received_at=None,
    reference: str = "",
    note: str = "",
    idempotency_key: str = "",
) -> Payment:
    """Record money the business received. Partial payments are allowed; overpayment is not."""
    invoice = _lock_invoice(invoice)
    amount = quantize(amount)
    existing = _existing_by_key(
        invoice.business, idempotency_key, invoice=invoice, kind=PaymentKind.PAYMENT, amount=amount
    )
    if existing:
        return existing
    if invoice.status != InvoiceStatus.ISSUED:
        raise ConflictError(
            "Payments can only be recorded on issued invoices.", code="invoice_void"
        )
    if amount <= ZERO:
        raise DomainError(
            "Enter an amount greater than zero.", fields={"amount": ["Must be greater than zero."]}
        )
    balance = invoice.total - invoice.amount_paid
    if amount > balance:
        raise ConflictError(
            f"The amount exceeds the outstanding balance of {invoice.currency} {balance}.",
            code="overpayment",
            fields={"amount": [f"At most {balance}."]},
            details={"balance_due": str(balance)},
        )
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                business=invoice.business,
                invoice=invoice,
                kind=PaymentKind.PAYMENT,
                method=method,
                amount=amount,
                received_at=received_at or timezone.now(),
                reference=reference,
                note=note,
                recorded_by=actor,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        # A concurrent request with the same key won the race.
        return _existing_by_key(
            invoice.business,
            idempotency_key,
            invoice=invoice,
            kind=PaymentKind.PAYMENT,
            amount=amount,
        )
    invoice.amount_paid += amount
    invoice.save(update_fields=["amount_paid", "updated_at"])
    _sync_order_payment_status(invoice)
    orders.add_event(
        invoice.order,
        kind=EventKind.PAYMENT,
        actor=actor,
        message=f"Payment of {invoice.currency} {amount} recorded ({payment.get_method_display()}). Balance {invoice.currency} {invoice.balance_due}.",
        visible_to_customer=True,
    )
    record(
        action="payment.recorded",
        entity=payment,
        business=invoice.business,
        actor=actor,
        changes={"invoice": invoice.reference, "amount": amount, "method": method},
        label=f"{invoice.reference} payment",
    )
    return payment


@transaction.atomic
def record_refund(
    *,
    payment: Payment,
    amount: Decimal,
    actor,
    reason: str,
    method: str | None = None,
    idempotency_key: str = "",
) -> Payment:
    """Record money returned to the customer, as a separate row that references the original payment."""
    invoice = _lock_invoice(payment.invoice)
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    amount = quantize(amount)
    existing = _existing_by_key(
        invoice.business, idempotency_key, invoice=invoice, kind=PaymentKind.REFUND, amount=amount
    )
    if existing:
        return existing
    if payment.kind != PaymentKind.PAYMENT:
        raise DomainError("Only payments can be refunded.", code="not_refundable")
    if not reason.strip():
        raise DomainError("Give a reason for the refund.", fields={"reason": ["Required."]})
    refunded = payment.refunds.aggregate(s=Sum("amount"))["s"] or ZERO
    refundable = payment.amount - refunded
    if amount <= ZERO or amount > refundable:
        raise ConflictError(
            f"You can refund at most {invoice.currency} {refundable} of this payment.",
            code="refund_exceeds_payment",
            fields={"amount": [f"At most {refundable}."]},
            details={"refundable": str(refundable)},
        )
    refund = Payment.objects.create(
        business=invoice.business,
        invoice=invoice,
        kind=PaymentKind.REFUND,
        method=method or payment.method,
        amount=amount,
        received_at=timezone.now(),
        note=reason.strip(),
        refund_of=payment,
        recorded_by=actor,
        idempotency_key=idempotency_key,
    )
    invoice.amount_paid -= amount
    invoice.save(update_fields=["amount_paid", "updated_at"])
    _sync_order_payment_status(invoice)
    orders.add_event(
        invoice.order,
        kind=EventKind.PAYMENT,
        actor=actor,
        message=f"Refund of {invoice.currency} {amount} recorded: {refund.note}",
        visible_to_customer=True,
    )
    record(
        action="payment.refunded",
        entity=refund,
        business=invoice.business,
        actor=actor,
        changes={
            "invoice": invoice.reference,
            "amount": amount,
            "refund_of": str(payment.public_id),
            "reason": refund.note,
        },
        label=f"{invoice.reference} refund",
    )
    return refund
