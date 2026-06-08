"""Two businesses side by side. Nothing of one may be visible or usable from the other."""

import uuid
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.businesses.models import Membership
from apps.core.tenancy import SESSION_KEY
from apps.estimates import services as estimates
from apps.inventory import services as inventory
from apps.invoicing import services as invoicing
from apps.orders import services as orders
from apps.orders.models import OrderStatus
from apps.scheduling import services as scheduling
from conftest import client_for

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def beta_records(other_shop, next_weekday_10am):
    """A complete set of records in the other business."""
    s = other_shop
    order = orders.create_order(business=s.business, customer=s.customer, device=s.device, problem_description="Battery", actor=s.manager, assigned_technician=s.technician)
    appointment = scheduling.book(business=s.business, customer=s.customer, technician=s.technician, starts_at=next_weekday_10am, duration_minutes=60, actor=s.manager, order=order)
    order = orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=s.technician)
    attachment = orders.add_attachment(order=order, upload=SimpleUploadedFile("photo.png", PNG), actor=s.manager, visible_to_customer=True)
    estimate = estimates.create_version(order=order, actor=s.manager)
    estimates.replace_lines(estimate=estimate, lines=[{"part": s.part, "quantity": Decimal("1")}], notes="", actor=s.manager)
    estimate, _ = estimates.send(estimate=estimate, actor=s.manager)
    estimates.decide(estimate=estimate, approve=True, channel="staff", decided_by=s.manager, decided_by_name="Customer")
    reservation, _ = inventory.reserve(order=order, part=s.part, quantity=Decimal("1"), actor=s.technician, idempotency_key="beta-1")
    inventory.consume(reservation=reservation, actor=s.technician)
    invoice = invoicing.issue_invoice(order=order, actor=s.manager)
    payment = invoicing.record_payment(invoice=invoice, amount=Decimal("10.00"), method="cash", actor=s.manager)
    return {
        "customer": s.customer,
        "device": s.device,
        "part": s.part,
        "order": order,
        "appointment": appointment,
        "attachment": attachment,
        "estimate": estimate,
        "reservation": reservation,
        "invoice": invoice,
        "payment": payment,
    }


def detail_urls(r):
    return [
        f"/api/v1/customers/{r['customer'].public_id}/",
        f"/api/v1/customers/{r['customer'].public_id}/notes/",
        f"/api/v1/customers/{r['customer'].public_id}/devices/",
        f"/api/v1/devices/{r['device'].public_id}/",
        f"/api/v1/parts/{r['part'].public_id}/",
        f"/api/v1/parts/{r['part'].public_id}/movements/",
        f"/api/v1/orders/{r['order'].public_id}/",
        f"/api/v1/orders/{r['order'].public_id}/timeline/",
        f"/api/v1/orders/{r['order'].public_id}/attachments/",
        f"/api/v1/orders/{r['order'].public_id}/attachments/{r['attachment'].public_id}/download/",
        f"/api/v1/appointments/{r['appointment'].public_id}/",
        f"/api/v1/estimates/{r['estimate'].public_id}/",
        f"/api/v1/invoices/{r['invoice'].public_id}/",
        f"/api/v1/invoices/{r['invoice'].public_id}/pdf/",
        f"/api/v1/payments/{r['payment'].public_id}/",
    ]


@pytest.mark.parametrize("role", ["owner", "manager"])
def test_records_of_another_business_are_not_found(shop, beta_records, role):
    client = shop.client(role)
    for url in detail_urls(beta_records):
        response = client.get(url)
        assert response.status_code == 404, url


def test_lists_never_include_another_business(shop, beta_records):
    client = shop.client("owner")
    beta_ids = {str(v.public_id) for v in beta_records.values() if hasattr(v, "public_id")}
    for url in ["/api/v1/customers/", "/api/v1/devices/", "/api/v1/orders/", "/api/v1/parts/", "/api/v1/invoices/", "/api/v1/stock-movements/", "/api/v1/notifications/", "/api/v1/audit-log/"]:
        data = client.get(url).data
        rows = data["results"] if isinstance(data, dict) else data
        assert not beta_ids & {str(row.get("id")) for row in rows}, url
    for url in ["/api/v1/appointments/?start=2000-01-01T00:00:00Z", "/api/v1/estimates/", "/api/v1/reservations/"]:
        assert client.get(url).data == [], url
    audit = client.get("/api/v1/audit-log/").data["results"]
    assert all("Beta" not in row["entity_label"] for row in audit)


def test_actions_on_another_business_are_not_found(shop, beta_records):
    client = shop.client("owner")
    r = beta_records
    attempts = [
        (f"/api/v1/orders/{r['order'].public_id}/transition/", {"to_status": "cancelled", "reason": "x"}),
        (f"/api/v1/orders/{r['order'].public_id}/notes/", {"body": "hi"}),
        (f"/api/v1/estimates/{r['estimate'].public_id}/send/", {}),
        (f"/api/v1/invoices/{r['invoice'].public_id}/payments/", {"amount": "1.00", "method": "cash"}),
        (f"/api/v1/payments/{r['payment'].public_id}/refund/", {"amount": "1.00", "reason": "x"}),
        (f"/api/v1/parts/{r['part'].public_id}/adjust/", {"counted_quantity": "100", "reason": "x"}),
        (f"/api/v1/reservations/{r['reservation'].public_id}/release/", {}),
        (f"/api/v1/appointments/{r['appointment'].public_id}/set_status/", {"status": "cancelled"}),
    ]
    for url, body in attempts:
        assert client.post(url, body).status_code == 404, url
    assert client.patch(f"/api/v1/customers/{r['customer'].public_id}/", {"full_name": "Hacked"}).status_code == 404


def test_relations_to_another_business_are_rejected(shop, beta_records, next_weekday_10am):
    client = shop.client("manager")
    r = beta_records
    # Order for a customer and device of the other business.
    response = client.post("/api/v1/orders/", {"customer": str(r["customer"].public_id), "device": str(r["device"].public_id), "problem_description": "x"})
    assert response.status_code == 400
    assert set(response.data["error"]["fields"]) >= {"customer", "device"}
    # Own customer with someone else's device.
    response = client.post("/api/v1/orders/", {"customer": str(shop.customer.public_id), "device": str(r["device"].public_id), "problem_description": "x"})
    assert response.status_code == 400 and "device" in response.data["error"]["fields"]
    # Technician who works for the other business.
    response = client.post(
        "/api/v1/orders/",
        {"customer": str(shop.customer.public_id), "device": str(shop.device.public_id), "problem_description": "x", "assigned_technician": str(beta_records["order"].assigned_technician.public_id)},
    )
    assert response.status_code == 400 and "assigned_technician" in response.data["error"]["fields"]
    # Device registered under another business's customer.
    response = client.post("/api/v1/devices/", {"customer": str(r["customer"].public_id), "brand": "X", "model": "Y"})
    assert response.status_code == 400
    # Reserving another business's part.
    own = orders.create_order(business=shop.business, customer=shop.customer, device=shop.device, problem_description="x", actor=shop.manager, assigned_technician=shop.technician)
    orders.transition(order=own, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    response = client.post("/api/v1/reservations/", {"order": str(own.public_id), "part": str(r["part"].public_id), "quantity": "1", "idempotency_key": "k1"})
    assert response.status_code == 400 and "part" in response.data["error"]["fields"]
    # Estimate line with another business's part.
    estimate = client.post("/api/v1/estimates/", {"order": str(own.public_id)}).data
    response = client.post(f"/api/v1/estimates/{estimate['id']}/lines/", {"lines": [{"part": str(r["part"].public_id), "quantity": "1"}]}, format="json")
    assert response.status_code == 400
    # Appointment for another business's customer.
    response = client.post(
        "/api/v1/appointments/",
        {"customer": str(r["customer"].public_id), "technician": str(shop.technician.public_id), "starts_at": next_weekday_10am.isoformat(), "duration_minutes": 30},
    )
    assert response.status_code == 400


def test_switching_to_a_workspace_without_membership_is_refused(shop, other_shop):
    client = shop.client("owner")
    response = client.post("/api/v1/workspaces/switch/", {"business_id": str(other_shop.business.public_id)})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "workspace_not_found"
    assert client.get("/api/v1/auth/session/").data["active_workspace"]["name"] == "Alpha Repairs"


def test_tampered_session_business_is_not_trusted(shop, other_shop):
    """Even if the session pointed at a business the user is not a member of, nothing is served."""
    client = client_for(shop.owner, other_shop.business)
    response = client.get("/api/v1/customers/")
    assert response.status_code == 403
    assert response.data["error"]["code"] == "no_active_workspace"
    assert SESSION_KEY not in client.session


def test_business_id_in_request_body_is_ignored(shop, other_shop):
    client = shop.client("manager")
    response = client.post("/api/v1/customers/", {"full_name": "Sneaky", "phone": "1", "business": other_shop.business.pk, "business_id": str(other_shop.business.public_id)})
    assert response.status_code == 201
    from apps.customers.models import Customer

    assert Customer.objects.get(public_id=response.data["id"]).business_id == shop.business.pk


def test_removed_member_loses_access_immediately(shop):
    client = shop.client("manager")
    assert client.get("/api/v1/orders/").status_code == 200
    Membership.objects.filter(business=shop.business, user=shop.manager).update(is_active=False)
    assert client.get("/api/v1/orders/").status_code == 403


def test_users_with_roles_in_two_businesses_see_each_separately(shop, other_shop):
    Membership.objects.create(business=other_shop.business, user=shop.manager, role="technician")
    client = shop.client("manager")
    assert client.get("/api/v1/customers/").data["count"] == 1
    session = client.post("/api/v1/workspaces/switch/", {"business_id": str(other_shop.business.public_id)}).data
    assert session["active_workspace"] == {**session["active_workspace"], "name": "Beta Fixers", "role": "technician"}
    # Now a technician there: no customers are assigned to them yet, and manager actions are refused.
    assert client.get("/api/v1/customers/").data["count"] == 0
    assert client.post("/api/v1/customers/", {"full_name": "X", "phone": "1"}).status_code == 403


def test_reports_and_exports_only_cover_the_active_business(shop, beta_records):
    client = shop.client("owner")
    dashboard = client.get("/api/v1/reports/dashboard/").data
    assert dashboard["collected"]["net"] == "0.00"
    assert sum(row["count"] for row in dashboard["orders_by_status"]) == 0
    for dataset in ["orders", "invoices", "payments", "parts", "customers"]:
        response = client.get(f"/api/v1/reports/export/{dataset}.csv")
        assert response.status_code == 200
        content = b"".join(response.streaming_content).decode()
        assert "Beta" not in content and "BETA" not in content, dataset


def test_random_uuids_are_plain_404s(shop):
    client = shop.client("owner")
    assert client.get(f"/api/v1/orders/{uuid.uuid4()}/").status_code == 404
