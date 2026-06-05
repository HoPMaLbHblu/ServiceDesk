"""The full repair lifecycle through the API, as each role would perform it."""

import re
import uuid
from decimal import Decimal

from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.inventory.models import Part
from apps.notifications.models import Notification, NotificationKind


def approval_token(order_number_ref: str) -> str:
    note = Notification.objects.filter(kind=NotificationKind.ESTIMATE_APPROVAL_REQUEST).latest(
        "created_at"
    )
    return re.search(r"/approve/([\w-]+)", note.body).group(1)


def test_full_repair_lifecycle(shop, next_weekday_10am):
    manager, tech = shop.client("manager"), shop.client("technician")

    # Manager takes the request and books a diagnosis appointment with the technician.
    response = manager.post(
        "/api/v1/orders/",
        {
            "customer": str(shop.customer.public_id),
            "device": str(shop.device.public_id),
            "problem_description": "Cracked screen",
            "priority": "high",
        },
    )
    assert response.status_code == 201, response.data
    order = response.data
    assert order["reference"] == "RO-00001" and order["status"] == "new"

    response = manager.post(
        "/api/v1/appointments/",
        {
            "customer": str(shop.customer.public_id),
            "order": order["id"],
            "technician": str(shop.technician.public_id),
            "starts_at": next_weekday_10am.isoformat(),
            "duration_minutes": 60,
        },
    )
    assert response.status_code == 201, response.data
    detail = manager.get(f"/api/v1/orders/{order['id']}/").data
    assert detail["status"] == "scheduled"
    assert detail["assigned_technician"]["id"] == str(shop.technician.public_id)

    # Technician diagnoses.
    response = tech.post(f"/api/v1/orders/{order['id']}/transition/", {"to_status": "diagnosing"})
    assert response.status_code == 200, response.data
    response = tech.post(
        f"/api/v1/orders/{order['id']}/diagnostics/", {"findings": "LCD cracked, digitizer OK"}
    )
    assert response.status_code == 200

    # Manager prepares and sends the estimate.
    estimate = manager.post("/api/v1/estimates/", {"order": order["id"]}).data
    response = manager.post(
        f"/api/v1/estimates/{estimate['id']}/lines/",
        {
            "lines": [
                {
                    "kind": "labor",
                    "description": "Screen replacement labor",
                    "quantity": "1",
                    "unit_price": "50.00",
                },
                {"part": str(shop.part.public_id), "quantity": "1"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["subtotal"] == "139.99"
    assert response.data["tax_total"] == "14.00"
    assert response.data["total"] == "153.99"
    response = manager.post(f"/api/v1/estimates/{estimate['id']}/send/")
    assert response.status_code == 200, response.data
    assert manager.get(f"/api/v1/orders/{order['id']}/").data["status"] == "awaiting_approval"

    # Customer approves through the emailed link, without logging in.
    token = approval_token(order["reference"])
    public = APIClient()
    page = public.get(f"/api/v1/public/approvals/{token}/").data
    assert page["total"] == "153.99" and page["link_state"] == "open"
    response = public.post(
        f"/api/v1/public/approvals/{token}/",
        {"decision": "approve", "name": "Pat Customer", "content_hash": page["content_hash"]},
    )
    assert response.status_code == 200, response.data
    assert response.data["status"] == "approved"
    assert manager.get(f"/api/v1/orders/{order['id']}/").data["status"] == "in_progress"
    # The link is single use.
    assert (
        public.post(
            f"/api/v1/public/approvals/{token}/", {"decision": "reject", "name": "x"}
        ).status_code
        == 400
    )

    # Technician reserves and consumes the part, then marks the device ready.
    key = str(uuid.uuid4())
    response = tech.post(
        "/api/v1/reservations/",
        {
            "order": order["id"],
            "part": str(shop.part.public_id),
            "quantity": "1",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.data
    reservation = response.data
    assert tech.post(f"/api/v1/reservations/{reservation['id']}/consume/").status_code == 200
    part = Part.objects.get(pk=shop.part.pk)
    assert part.quantity_on_hand == Decimal("4") and part.quantity_reserved == Decimal("0")
    response = tech.post(
        f"/api/v1/orders/{order['id']}/transition/", {"to_status": "ready_for_pickup"}
    )
    assert response.status_code == 200, response.data

    # Manager invoices, takes two payments, and hands the device back.
    response = manager.post("/api/v1/invoices/", {"order": order["id"]})
    assert response.status_code == 201, response.data
    invoice = response.data
    assert invoice["reference"] == "INV-00001" and invoice["total"] == "153.99"
    assert (
        manager.post(
            f"/api/v1/invoices/{invoice['id']}/payments/", {"amount": "100.00", "method": "card"}
        ).status_code
        == 201
    )
    assert manager.get(f"/api/v1/orders/{order['id']}/").data["payment_status"] == "partially_paid"
    response = manager.post(
        f"/api/v1/invoices/{invoice['id']}/payments/", {"amount": "60.00", "method": "cash"}
    )
    assert response.status_code == 409 and response.data["error"]["code"] == "overpayment"
    assert (
        manager.post(
            f"/api/v1/invoices/{invoice['id']}/payments/", {"amount": "53.99", "method": "cash"}
        ).status_code
        == 201
    )
    invoice = manager.get(f"/api/v1/invoices/{invoice['id']}/").data
    assert invoice["balance_due"] == "0.00"

    response = manager.post(f"/api/v1/orders/{order['id']}/transition/", {"to_status": "completed"})
    assert response.status_code == 200, response.data
    final = response.data
    assert final["status"] == "completed" and final["payment_status"] == "paid"
    assert final["allowed_transitions"] == []

    # The timeline and audit log captured the important steps.
    kinds = [e["kind"] for e in manager.get(f"/api/v1/orders/{order['id']}/timeline/").data]
    assert kinds.count("status_changed") >= 6
    actions = set(AuditLog.objects.filter(business=shop.business).values_list("action", flat=True))
    assert {
        "order.created",
        "order.status_changed",
        "estimate.sent",
        "estimate.approved",
        "invoice.issued",
        "payment.recorded",
    } <= actions
