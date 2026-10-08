import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.exceptions import ConflictError
from apps.core.money import compute_totals, line_total
from apps.estimates import services as estimates
from apps.estimates.models import Estimate, EstimateStatus
from apps.notifications.models import Notification, NotificationKind
from apps.orders import services as orders
from apps.orders.models import OrderStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def diagnosing_order(shop):
    order = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    return orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)


def sent_estimate(shop, order, price="100.00"):
    estimate = estimates.create_version(order=order, actor=shop.manager)
    estimates.replace_lines(
        estimate=estimate,
        lines=[{"description": "Labor", "quantity": Decimal("1"), "unit_price": Decimal(price)}],
        notes=None,
        actor=shop.manager,
    )
    estimate, raw = estimates.send(estimate=estimate, actor=shop.manager)
    return estimate, raw


class TestMoney:
    def test_line_totals_round_half_up(self):
        assert line_total(Decimal("3"), Decimal("0.335")) == Decimal("1.01")
        assert line_total(Decimal("0.5"), Decimal("19.99")) == Decimal("10.00")

    def test_tax_only_on_taxable_lines_and_rounded_once(self):
        totals = compute_totals(
            [(Decimal("10.01"), True), (Decimal("10.01"), True), (Decimal("50.00"), False)],
            Decimal("8.25"),
        )
        assert totals.subtotal == Decimal("70.02")
        assert totals.tax_total == Decimal("1.65")  # 20.02 * 0.0825 = 1.65165
        assert totals.total == Decimal("71.67")

    def test_no_float_artifacts(self):
        totals = compute_totals([(line_total(Decimal("3"), Decimal("0.10")), True)], Decimal("0"))
        assert totals.total == Decimal("0.30")


def test_approval_refers_to_a_specific_version(shop, diagnosing_order):
    v1, token_v1 = sent_estimate(shop, diagnosing_order, "100.00")
    # Revising the quote supersedes v1 immediately; its link stops working.
    v2 = estimates.create_version(order=diagnosing_order, actor=shop.manager)
    assert [line.unit_price for line in v2.lines.all()] == [Decimal("100.00")]
    v1.refresh_from_db()
    assert v1.status == EstimateStatus.SUPERSEDED
    with pytest.raises(ConflictError) as exc:
        estimates.decide(estimate=v1, approve=True, channel="link", decided_by_name="C")
    assert exc.value.error_code == "estimate_not_pending"
    page = APIClient().get(f"/api/v1/public/approvals/{token_v1}/").data
    assert page["status"] == "superseded" and page["link_state"] == "expired"


def test_changing_an_approved_estimate_requires_new_approval(shop, diagnosing_order):
    v1, _ = sent_estimate(shop, diagnosing_order)
    estimates.decide(
        estimate=v1, approve=True, channel="staff", decided_by=shop.manager, decided_by_name="C"
    )
    diagnosing_order.refresh_from_db()
    assert diagnosing_order.status == OrderStatus.IN_PROGRESS
    # Approved versions are locked.
    with pytest.raises(ConflictError):
        estimates.replace_lines(estimate=v1, lines=[], notes=None, actor=shop.manager)
    # Additional work: a new version, sent again, puts the order back to awaiting approval.
    v2 = estimates.create_version(order=diagnosing_order, actor=shop.manager)
    estimates.replace_lines(
        estimate=v2,
        lines=[
            {"description": "Labor", "quantity": Decimal("1"), "unit_price": Decimal("100")},
            {"description": "Extra", "quantity": Decimal("1"), "unit_price": Decimal("25")},
        ],
        notes=None,
        actor=shop.manager,
    )
    estimates.send(estimate=v2, actor=shop.manager)
    v1.refresh_from_db()
    diagnosing_order.refresh_from_db()
    assert v1.status == EstimateStatus.SUPERSEDED
    assert diagnosing_order.status == OrderStatus.AWAITING_APPROVAL
    response = shop.client("manager").post(
        f"/api/v1/orders/{diagnosing_order.public_id}/transition/", {"to_status": "in_progress"}
    )
    assert response.data["error"]["code"] == "estimate_not_approved"


def test_historical_prices_survive_catalog_changes(shop, diagnosing_order):
    estimate = estimates.create_version(order=diagnosing_order, actor=shop.manager)
    estimates.replace_lines(
        estimate=estimate,
        lines=[{"part": shop.part, "quantity": Decimal("2")}],
        notes=None,
        actor=shop.manager,
    )
    estimates.send(estimate=estimate, actor=shop.manager)
    shop.part.selling_price = Decimal("150.00")
    shop.part.name = "Renamed"
    shop.part.save()
    line = Estimate.objects.get(pk=estimate.pk).lines.get()
    assert (line.unit_price, line.description, line.line_total) == (
        Decimal("89.99"),
        "Screen assembly",
        Decimal("179.98"),
    )
    estimates.decide(
        estimate=estimate,
        approve=True,
        channel="staff",
        decided_by=shop.manager,
        decided_by_name="C",
    )


def test_content_hash_mismatch_blocks_approval(shop, diagnosing_order):
    estimate, token = sent_estimate(shop, diagnosing_order)
    response = APIClient().post(
        f"/api/v1/public/approvals/{token}/",
        {"decision": "approve", "name": "C", "content_hash": "0" * 64},
    )
    assert response.status_code == 409 and response.data["error"]["code"] == "estimate_changed"


def test_expired_estimate_cannot_be_approved(shop, diagnosing_order):
    estimate, token = sent_estimate(shop, diagnosing_order)
    Estimate.objects.filter(pk=estimate.pk).update(
        valid_until=timezone.now().date() - timedelta(days=2)
    )
    response = APIClient().post(
        f"/api/v1/public/approvals/{token}/", {"decision": "approve", "name": "C"}
    )
    assert response.status_code == 409 and response.data["error"]["code"] == "estimate_expired"


def test_approval_records_identity_and_timestamp(shop, diagnosing_order):
    estimate, token = sent_estimate(shop, diagnosing_order)
    APIClient().post(
        f"/api/v1/public/approvals/{token}/",
        {"decision": "approve", "name": "Pat Customer", "note": "Go ahead"},
    )
    estimate.refresh_from_db()
    assert estimate.decided_by_name == "Pat Customer" and estimate.decision_channel == "link"
    assert estimate.decided_at is not None and estimate.decision_note == "Go ahead"
    from apps.audit.models import AuditLog

    log = AuditLog.objects.get(action="estimate.approved")
    assert log.changes["version"] == 1 and log.changes["content_hash"] == estimate.content_hash


def test_unknown_token_reveals_nothing():
    response = APIClient().get("/api/v1/public/approvals/not-a-real-token/")
    assert response.status_code == 400 and response.data["error"]["code"] == "invalid_token"


def test_approval_email_is_queued_once(shop, diagnosing_order):
    sent_estimate(shop, diagnosing_order)
    assert Notification.objects.filter(kind=NotificationKind.ESTIMATE_APPROVAL_REQUEST).count() == 1
    body = Notification.objects.get(kind=NotificationKind.ESTIMATE_APPROVAL_REQUEST).body
    assert re.search(r"/approve/[\w-]{20,}", body)


def test_estimate_total_too_large_is_a_validation_error(shop, diagnosing_order):
    estimate = estimates.create_version(order=diagnosing_order, actor=shop.manager)
    client = shop.client("manager")
    url = f"/api/v1/estimates/{estimate.public_id}/lines/"
    huge = {"description": "x", "quantity": "99999999", "unit_price": "99999999"}
    response = client.post(url, {"lines": [huge]}, format="json")
    assert response.status_code == 400
    assert "lines.0.quantity" in response.data["error"]["fields"]
    ok = {"description": "x", "quantity": "2", "unit_price": "10"}
    assert client.post(url, {"lines": [ok]}, format="json").status_code == 200
