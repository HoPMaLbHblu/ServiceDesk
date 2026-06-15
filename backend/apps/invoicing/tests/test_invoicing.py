from decimal import Decimal

import pytest

from apps.core.exceptions import ConflictError
from apps.estimates import services as estimates
from apps.invoicing import services as invoicing
from apps.invoicing.models import Invoice
from apps.invoicing.pdf import render_invoice
from apps.orders import services as orders
from apps.orders.models import OrderStatus, PaymentStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice(shop):
    order = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    estimate = estimates.create_version(order=order, actor=shop.manager)
    estimates.replace_lines(
        estimate=estimate,
        lines=[
            {"description": "Labor", "quantity": Decimal("1.5"), "unit_price": Decimal("40.00")},
            {
                "description": "Cleaning kit",
                "quantity": Decimal("1"),
                "unit_price": Decimal("9.99"),
                "taxable": False,
            },
        ],
        notes=None,
        actor=shop.manager,
    )
    estimates.send(estimate=estimate, actor=shop.manager)
    estimates.decide(
        estimate=estimate,
        approve=True,
        channel="staff",
        decided_by=shop.manager,
        decided_by_name="C",
    )
    return invoicing.issue_invoice(order=order, actor=shop.manager)


def test_invoice_snapshots_estimate_totals(invoice):
    assert invoice.subtotal == Decimal("69.99")
    assert invoice.tax_total == Decimal("6.00")  # 10% of 60.00 taxable
    assert invoice.total == Decimal("75.99")
    assert invoice.lines.count() == 2
    assert invoice.customer_snapshot["name"] == "Alpha Repairs Customer"


def test_customer_edits_do_not_change_issued_invoice(shop, invoice):
    shop.customer.full_name = "Someone Else"
    shop.customer.save()
    invoice.refresh_from_db()
    assert invoice.customer_snapshot["name"] == "Alpha Repairs Customer"


def test_partial_payments_refunds_and_balances(shop, invoice):
    p1 = invoicing.record_payment(
        invoice=invoice, amount=Decimal("50.00"), method="card", actor=shop.manager
    )
    invoice.refresh_from_db()
    assert invoice.balance_due == Decimal("25.99")
    assert invoice.order.payment_status == PaymentStatus.PARTIALLY_PAID
    invoicing.record_payment(
        invoice=invoice, amount=Decimal("25.99"), method="cash", actor=shop.manager
    )
    invoice.refresh_from_db()
    assert (
        invoice.balance_due == Decimal("0.00")
        and invoice.order.payment_status == PaymentStatus.PAID
    )

    with pytest.raises(ConflictError) as exc:
        invoicing.record_refund(payment=p1, amount=Decimal("60.00"), actor=shop.manager, reason="x")
    assert exc.value.error_code == "refund_exceeds_payment"
    invoicing.record_refund(
        payment=p1, amount=Decimal("20.00"), actor=shop.manager, reason="Goodwill"
    )
    invoicing.record_refund(payment=p1, amount=Decimal("30.00"), actor=shop.manager, reason="Rest")
    with pytest.raises(ConflictError):
        invoicing.record_refund(
            payment=p1, amount=Decimal("0.01"), actor=shop.manager, reason="Too much"
        )
    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("25.99")
    assert invoice.order.payment_status == PaymentStatus.PARTIALLY_PAID
    # The original payment rows are untouched; refunds are separate rows.
    assert p1.amount == Decimal("50.00")
    assert invoice.payments.filter(kind="refund").count() == 2


def test_overpayment_is_refused(shop, invoice):
    with pytest.raises(ConflictError) as exc:
        invoicing.record_payment(
            invoice=invoice, amount=Decimal("76.00"), method="cash", actor=shop.manager
        )
    assert exc.value.error_code == "overpayment"


def test_payment_idempotency_key(shop, invoice):
    first = invoicing.record_payment(
        invoice=invoice,
        amount=Decimal("10.00"),
        method="cash",
        actor=shop.manager,
        idempotency_key="pay-1",
    )
    again = invoicing.record_payment(
        invoice=invoice,
        amount=Decimal("10.00"),
        method="cash",
        actor=shop.manager,
        idempotency_key="pay-1",
    )
    assert first.pk == again.pk
    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("10.00")
    with pytest.raises(ConflictError):
        invoicing.record_payment(
            invoice=invoice,
            amount=Decimal("11.00"),
            method="cash",
            actor=shop.manager,
            idempotency_key="pay-1",
        )


def test_payment_api_rejects_negative_and_zero_amounts(shop, invoice):
    client = shop.client("manager")
    for amount in ["0", "-5.00", "abc"]:
        response = client.post(
            f"/api/v1/invoices/{invoice.public_id}/payments/", {"amount": amount, "method": "cash"}
        )
        assert response.status_code == 400 and "amount" in response.data["error"]["fields"]


def test_void_rules(shop, invoice):
    invoicing.record_payment(
        invoice=invoice, amount=Decimal("5.00"), method="cash", actor=shop.manager
    )
    with pytest.raises(ConflictError) as exc:
        invoicing.void_invoice(invoice=invoice, reason="Wrong", actor=shop.manager)
    assert exc.value.error_code == "invoice_has_payments"


def test_numbering_and_one_issued_invoice_per_order(shop, invoice):
    assert invoice.number == 1
    with pytest.raises(ConflictError):
        invoicing.issue_invoice(order=invoice.order, actor=shop.manager)
    invoicing.void_invoice(invoice=invoice, reason="Typo", actor=shop.manager)
    reissued = invoicing.issue_invoice(order=invoice.order, actor=shop.manager)
    assert reissued.number == 2
    assert Invoice.objects.filter(order=invoice.order).count() == 2


def test_pdf_renders(shop, invoice):
    pdf = render_invoice(invoice)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    response = shop.client("manager").get(f"/api/v1/invoices/{invoice.public_id}/pdf/")
    assert response.status_code == 200 and response["Content-Type"] == "application/pdf"
