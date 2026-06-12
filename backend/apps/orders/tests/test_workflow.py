from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction

from apps.estimates import services as estimates
from apps.orders import services as orders
from apps.orders.models import OrderEvent, OrderStatus
from conftest import client_for, make_user

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def order(shop):
    return orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="No power",
        actor=shop.manager,
    )


def post_transition(client, order, to_status, **extra):
    return client.post(
        f"/api/v1/orders/{order.public_id}/transition/", {"to_status": to_status, **extra}
    )


def test_order_numbers_are_sequential_per_business(shop, other_shop):
    a1 = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.owner,
    )
    b1 = orders.create_order(
        business=other_shop.business,
        customer=other_shop.customer,
        device=other_shop.device,
        problem_description="x",
        actor=other_shop.owner,
    )
    a2 = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.owner,
    )
    assert (a1.number, a2.number, b1.number) == (1, 2, 1)


@pytest.mark.parametrize(
    ("target", "code"),
    [
        ("in_progress", "invalid_transition"),
        ("ready_for_pickup", "invalid_transition"),
        ("completed", "invalid_transition"),
        ("awaiting_approval", "invalid_transition"),
    ],
)
def test_invalid_transitions_from_new_are_refused(shop, order, target, code):
    response = post_transition(shop.client("manager"), order, target)
    assert response.status_code == 409
    assert response.data["error"]["code"] == code
    assert "allowed" in response.data["error"]["details"]


def test_guards_explain_what_is_missing(shop, order):
    client = shop.client("manager")
    response = post_transition(client, order, "diagnosing")
    assert response.data["error"]["code"] == "technician_required"
    response = post_transition(client, order, "scheduled")
    assert response.data["error"]["code"] == "system_transition"
    order.assigned_technician = shop.technician
    order.save()
    assert post_transition(client, order, "diagnosing").status_code == 200
    response = post_transition(client, order, "awaiting_approval")
    assert response.data["error"]["code"] == "system_transition"


def test_cancellation_needs_a_reason_and_is_terminal(shop, order):
    client = shop.client("manager")
    response = post_transition(client, order, "cancelled")
    assert response.status_code == 400 and response.data["error"]["code"] == "reason_required"
    response = post_transition(client, order, "cancelled", reason="Customer changed their mind")
    assert response.status_code == 200 and response.data["allowed_transitions"] == []
    # Closed orders are not silently reopened or edited.
    assert post_transition(client, order, "new").status_code == 409
    response = client.patch(
        f"/api/v1/orders/{order.public_id}/", {"version": 3, "priority": "urgent"}
    )
    assert response.status_code == 409 and response.data["error"]["code"] == "order_closed"


def test_cancelling_releases_reserved_parts(shop, order):
    from apps.inventory import services as inventory

    order.assigned_technician = shop.technician
    order.save()
    orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    inventory.reserve(
        order=order, part=shop.part, quantity=Decimal("2"), actor=shop.manager, idempotency_key="c1"
    )
    shop.part.refresh_from_db()
    assert shop.part.quantity_reserved == Decimal("2")
    orders.transition(
        order=order, to_status=OrderStatus.CANCELLED, actor=shop.manager, reason="No longer needed"
    )
    shop.part.refresh_from_db()
    assert shop.part.quantity_reserved == Decimal("0") and shop.part.quantity_on_hand == Decimal(
        "5"
    )


def test_technician_only_sees_and_moves_assigned_orders(shop, order):
    tech = shop.client("technician")
    assert tech.get("/api/v1/orders/").data["count"] == 0
    assert tech.get(f"/api/v1/orders/{order.public_id}/").status_code == 404
    order.assigned_technician = shop.technician
    order.save()
    assert tech.get("/api/v1/orders/").data["count"] == 1
    detail = tech.get(f"/api/v1/orders/{order.public_id}/").data
    assert detail["allowed_transitions"] == ["diagnosing"]
    assert post_transition(tech, order, "cancelled", reason="x").status_code == 409
    assert post_transition(tech, order, "diagnosing").status_code == 200
    # Technicians cannot edit order details or create orders.
    assert (
        tech.patch(
            f"/api/v1/orders/{order.public_id}/", {"version": 2, "priority": "low"}
        ).status_code
        == 403
    )


def test_stale_version_is_a_conflict(shop, order):
    client = shop.client("manager")
    assert (
        client.patch(
            f"/api/v1/orders/{order.public_id}/", {"version": 1, "priority": "high"}
        ).status_code
        == 200
    )
    response = client.patch(f"/api/v1/orders/{order.public_id}/", {"version": 1, "priority": "low"})
    assert response.status_code == 409
    assert response.data["error"]["code"] == "stale_version"
    assert response.data["error"]["details"]["current_version"] == 2


def test_in_progress_requires_the_latest_estimate_approved(shop, order):
    order.assigned_technician = shop.technician
    order.save()
    orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    estimate = estimates.create_version(order=order, actor=shop.manager)
    estimates.replace_lines(
        estimate=estimate,
        lines=[{"description": "Labor", "quantity": Decimal("1"), "unit_price": Decimal("20")}],
        notes=None,
        actor=shop.manager,
    )
    estimates.send(estimate=estimate, actor=shop.manager)
    estimates.decide(
        estimate=estimate,
        approve=False,
        channel="staff",
        decided_by=shop.manager,
        decided_by_name="Customer",
    )
    order.refresh_from_db()
    assert order.status == OrderStatus.AWAITING_APPROVAL
    response = post_transition(shop.client("manager"), order, "in_progress")
    assert response.status_code == 409 and response.data["error"]["code"] == "estimate_not_approved"
    assert post_transition(shop.client("manager"), order, "diagnosing").status_code == 200


def test_completion_requires_an_invoice(shop, order):
    order.status = OrderStatus.READY_FOR_PICKUP
    order.save()
    response = post_transition(shop.client("manager"), order, "completed")
    assert response.data["error"]["code"] == "invoice_required"


def test_internal_notes_are_separate_from_customer_updates(shop, order):
    client = shop.client("manager")
    client.post(
        f"/api/v1/orders/{order.public_id}/notes/",
        {"body": "Customer was rude", "visible_to_customer": False},
    )
    client.post(
        f"/api/v1/orders/{order.public_id}/notes/",
        {"body": "Parts ordered", "visible_to_customer": True},
    )
    events = {e.message: e for e in OrderEvent.objects.filter(order=order)}
    assert (
        events["Customer was rude"].kind == "internal_note"
        and not events["Customer was rude"].visible_to_customer
    )
    assert (
        events["Parts ordered"].kind == "customer_update"
        and events["Parts ordered"].visible_to_customer
    )


def test_timeline_is_immutable_in_the_database(order):
    event = OrderEvent.objects.filter(order=order).first()
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderEvent.objects.filter(pk=event.pk).update(message="rewritten")
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM orders_orderevent WHERE id = %s", [event.pk])


class TestAttachments:
    def upload(self, client, order, content=PNG, name="photo.png", **extra):
        return client.post(
            f"/api/v1/orders/{order.public_id}/attachments/",
            {"file": SimpleUploadedFile(name, content), **extra},
            format="multipart",
        )

    def test_upload_detects_type_from_content(self, shop, order):
        client = shop.client("manager")
        response = self.upload(client, order, name="evil.png", content=b"<script>alert(1)</script>")
        assert (
            response.status_code == 400
            and response.data["error"]["code"] == "file_type_not_allowed"
        )
        response = self.upload(client, order, name="invoice.exe", content=b"%PDF-1.7 fake")
        assert response.status_code == 201
        assert response.data["content_type"] == "application/pdf"

    def test_size_limit(self, shop, order, settings):
        settings.MAX_UPLOAD_SIZE = 100
        response = self.upload(shop.client("manager"), order, content=PNG + b"\x00" * 200)
        assert response.status_code == 400 and response.data["error"]["code"] == "file_too_large"

    def test_download_is_authorized(self, shop, other_shop, order):
        client = shop.client("manager")
        attachment = self.upload(client, order).data
        url = f"/api/v1/orders/{order.public_id}/attachments/{attachment['id']}/download/"
        response = client.get(url)
        assert response.status_code == 200
        assert response["Cache-Control"] == "private, no-store"
        assert b"".join(response.streaming_content) == PNG
        # Technician not assigned to the order, another business, and anonymous users are refused.
        assert shop.client("technician").get(url).status_code == 404
        assert other_shop.client("owner").get(url).status_code == 404
        from rest_framework.test import APIClient

        assert APIClient().get(url).status_code == 401
        assert client_for(make_user("nobody@example.com")).get(url).status_code == 403
