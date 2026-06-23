import re
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.customers.models import Customer, CustomerNote, CustomerPortalAccess, Device
from apps.estimates import services as estimates
from apps.notifications.models import Notification, NotificationKind
from apps.orders import services as orders
from apps.orders.models import OrderStatus
from conftest import client_for, make_user

pytestmark = pytest.mark.django_db
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
def portal(shop):
    """A portal user linked to the shop's customer, plus a second customer in the same shop."""
    user = make_user("pat@example.com", "Pat Customer")
    CustomerPortalAccess.objects.create(customer=shop.customer, user=user)
    neighbour = Customer.objects.create(business=shop.business, full_name="Neighbour", phone="1")
    neighbour_device = Device.objects.create(
        business=shop.business, customer=neighbour, brand="Samsung", model="S22"
    )
    own = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="Mine",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    theirs = orders.create_order(
        business=shop.business,
        customer=neighbour,
        device=neighbour_device,
        problem_description="Theirs",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    return {"client": client_for(user), "user": user, "own": own, "theirs": theirs}


def awaiting(shop, order):
    orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    estimate = estimates.create_version(order=order, actor=shop.manager)
    estimates.replace_lines(
        estimate=estimate,
        lines=[{"description": "Labor", "quantity": Decimal("1"), "unit_price": Decimal("30")}],
        notes=None,
        actor=shop.manager,
    )
    estimate, _ = estimates.send(estimate=estimate, actor=shop.manager)
    return estimate


def test_portal_only_lists_linked_customer_records(shop, portal):
    client = portal["client"]
    orders_list = client.get("/api/v1/portal/orders/").data
    assert [o["id"] for o in orders_list] == [str(portal["own"].public_id)]
    assert client.get(f"/api/v1/portal/orders/{portal['theirs'].public_id}/").status_code == 404
    assert [c["full_name"] for c in client.get("/api/v1/portal/customers/").data] == [
        "Alpha Repairs Customer"
    ]


def test_portal_hides_internal_information(shop, portal):
    order = portal["own"]
    CustomerNote.objects.create(business=shop.business, customer=shop.customer, body="Pays late")
    orders.add_note(
        order=order,
        body="Internal: check for water damage",
        visible_to_customer=False,
        actor=shop.manager,
    )
    orders.add_note(
        order=order, body="We received your phone", visible_to_customer=True, actor=shop.manager
    )
    hidden = orders.add_attachment(
        order=order,
        upload=SimpleUploadedFile("a.png", PNG),
        actor=shop.manager,
        visible_to_customer=False,
    )
    shown = orders.add_attachment(
        order=order,
        upload=SimpleUploadedFile("b.png", PNG),
        actor=shop.manager,
        visible_to_customer=True,
    )
    detail = portal["client"].get(f"/api/v1/portal/orders/{order.public_id}/").data
    messages = [e["message"] for e in detail["timeline"]]
    assert "We received your phone" in messages
    assert not any("Internal" in m for m in messages)
    assert [a["id"] for a in detail["attachments"]] == [str(shown.public_id)]
    assert "internal_notes" not in detail and "assigned_technician" not in detail
    base = f"/api/v1/portal/orders/{order.public_id}/attachments"
    assert portal["client"].get(f"{base}/{shown.public_id}/download/").status_code == 200
    assert portal["client"].get(f"{base}/{hidden.public_id}/download/").status_code == 404
    # Staff endpoints are not available to a portal-only user.
    assert portal["client"].get("/api/v1/customers/").status_code == 403


def test_portal_user_approves_own_estimate_only(shop, portal):
    own_estimate = awaiting(shop, portal["own"])
    their_estimate = awaiting(shop, portal["theirs"])
    client = portal["client"]
    assert (
        client.post(
            f"/api/v1/portal/estimates/{their_estimate.public_id}/decision/",
            {"decision": "approve"},
        ).status_code
        == 404
    )
    detail = client.get(f"/api/v1/portal/orders/{portal['own'].public_id}/").data
    assert [e["status"] for e in detail["estimates"]] == ["sent"]
    response = client.post(
        f"/api/v1/portal/estimates/{own_estimate.public_id}/decision/",
        {"decision": "approve", "content_hash": detail["estimates"][0]["content_hash"]},
    )
    assert response.status_code == 200 and response.data["status"] == "approved"
    own_estimate.refresh_from_db()
    assert own_estimate.decision_channel == "portal" and own_estimate.decided_by == portal["user"]


def test_draft_estimates_are_not_visible_in_portal(shop, portal):
    orders.transition(order=portal["own"], to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    estimates.create_version(order=portal["own"], actor=shop.manager)
    detail = portal["client"].get(f"/api/v1/portal/orders/{portal['own'].public_id}/").data
    assert detail["estimates"] == []


def test_revoked_portal_access_takes_effect_immediately(shop, portal):
    CustomerPortalAccess.objects.filter(user=portal["user"]).update(
        revoked_at="2020-01-01T00:00:00Z"
    )
    assert portal["client"].get("/api/v1/portal/orders/").data == []


def test_repair_request_from_portal(shop, portal):
    response = portal["client"].post(
        "/api/v1/portal/orders/",
        {
            "customer": str(shop.customer.public_id),
            "device_brand": "Google",
            "device_model": "Pixel 8",
            "problem_description": "Battery drains",
        },
    )
    assert response.status_code == 201, response.data
    assert response.data["status"] == "new"
    from apps.orders.models import RepairOrder

    order = RepairOrder.objects.get(public_id=response.data["id"])
    assert (
        order.source == "portal"
        and order.customer == shop.customer
        and order.device.model == "Pixel 8"
    )
    neighbour = Customer.objects.get(full_name="Neighbour")
    response = portal["client"].post(
        "/api/v1/portal/orders/",
        {
            "customer": str(neighbour.public_id),
            "device_brand": "x",
            "device_model": "y",
            "problem_description": "z",
        },
    )
    assert response.status_code == 404


def test_portal_invitation_links_account(shop):
    client = shop.client("manager")
    assert (
        client.post(
            f"/api/v1/customers/{shop.customer.public_id}/invite_to_portal/",
            {"email": "customer@alpha.test"},
        ).status_code
        == 202
    )
    token = re.search(
        r"token=([\w-]+)", Notification.objects.get(kind=NotificationKind.PORTAL_ACCESS).body
    ).group(1)
    wrong = client_for(make_user("wrong@example.com"))
    assert wrong.post("/api/v1/portal/accept/", {"token": token}).status_code == 400
    right_user = make_user("customer@alpha.test", verified=False)
    right = client_for(right_user)
    assert right.post("/api/v1/portal/accept/", {"token": token}).status_code == 204
    assert (
        right.get("/api/v1/auth/session/").data["portal_links"][0]["customer_name"]
        == "Alpha Repairs Customer"
    )
    assert right.post("/api/v1/portal/accept/", {"token": token}).status_code == 400
