from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.core.exceptions import ConflictError, DomainError
from apps.core.tests.concurrency import run_concurrently
from apps.inventory import services as inventory
from apps.inventory.models import MovementKind, Part, PartReservation, StockMovement
from apps.notifications.models import Notification, NotificationKind
from apps.orders import services as orders
from apps.orders.models import OrderStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def order(shop):
    order = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    return orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrent_reservations_never_oversell(shop, order):
    def reserve(key):
        reservation, _ = inventory.reserve(
            order=order,
            part=shop.part,
            quantity=Decimal("1"),
            actor=shop.technician,
            idempotency_key=key,
        )
        return reservation

    results = run_concurrently(reserve, [(f"k{i}",) for i in range(10)])
    succeeded = [r for r in results if isinstance(r, PartReservation)]
    refused = [r for r in results if isinstance(r, ConflictError)]
    assert len(succeeded) == 5 and len(refused) == 5, results
    assert all(r.error_code == "insufficient_stock" for r in refused)
    part = Part.objects.get(pk=shop.part.pk)
    assert part.quantity_reserved == Decimal("5") and part.quantity_on_hand == Decimal("5")
    assert StockMovement.objects.filter(part=part, kind=MovementKind.RESERVATION).count() == 5


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrent_duplicate_reservation_requests_reserve_once(shop, order):
    def reserve():
        return inventory.reserve(
            order=order,
            part=shop.part,
            quantity=Decimal("2"),
            actor=shop.technician,
            idempotency_key="same-key",
        )

    results = run_concurrently(reserve, [() for _ in range(6)])
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sum(1 for _, created in results if created) == 1
    assert Part.objects.get(pk=shop.part.pk).quantity_reserved == Decimal("2")


@pytest.mark.django_db(transaction=True)
@pytest.mark.concurrency
def test_concurrent_duplicate_consumption_consumes_once(shop, order):
    reservation, _ = inventory.reserve(
        order=order,
        part=shop.part,
        quantity=Decimal("3"),
        actor=shop.technician,
        idempotency_key="c",
    )
    results = run_concurrently(
        lambda: inventory.consume(reservation=reservation, actor=shop.technician),
        [() for _ in range(5)],
    )
    assert not [r for r in results if isinstance(r, Exception)], results
    assert sum(1 for _, changed in results if changed) == 1
    part = Part.objects.get(pk=shop.part.pk)
    assert part.quantity_on_hand == Decimal("2") and part.quantity_reserved == Decimal("0")
    assert (
        StockMovement.objects.filter(reservation=reservation, kind=MovementKind.CONSUMPTION).count()
        == 1
    )


def test_repeated_consume_and_release_are_safe(shop, order):
    reservation, _ = inventory.reserve(
        order=order,
        part=shop.part,
        quantity=Decimal("1"),
        actor=shop.technician,
        idempotency_key="r",
    )
    client = shop.client("technician")
    url = f"/api/v1/reservations/{reservation.public_id}"
    assert client.post(f"{url}/consume/").status_code == 200
    assert client.post(f"{url}/consume/").status_code == 200
    response = client.post(f"{url}/release/")
    assert response.status_code == 409 and response.data["error"]["code"] == "reservation_consumed"
    assert Part.objects.get(pk=shop.part.pk).quantity_on_hand == Decimal("4")


def test_reserve_endpoint_is_idempotent(shop, order):
    client = shop.client("technician")
    body = {
        "order": str(order.public_id),
        "part": str(shop.part.public_id),
        "quantity": "2",
        "idempotency_key": "abc",
    }
    first = client.post("/api/v1/reservations/", body)
    second = client.post("/api/v1/reservations/", body)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.data["id"] == second.data["id"]
    response = client.post("/api/v1/reservations/", {**body, "quantity": "3"})
    assert response.status_code == 409 and response.data["error"]["code"] == "idempotency_conflict"


def test_insufficient_stock_is_a_structured_conflict(shop, order):
    response = shop.client("manager").post(
        "/api/v1/reservations/",
        {
            "order": str(order.public_id),
            "part": str(shop.part.public_id),
            "quantity": "9",
            "idempotency_key": "x",
        },
    )
    assert response.status_code == 409
    assert response.data["error"]["code"] == "insufficient_stock"
    assert response.data["error"]["details"] == {
        "part": str(shop.part.public_id),
        "available": "5.00",
        "requested": "9.00",
    }


def test_stock_cannot_be_edited_directly(shop):
    client = shop.client("manager")
    response = client.patch(
        f"/api/v1/parts/{shop.part.public_id}/", {"quantity_on_hand": "999", "name": "Renamed"}
    )
    assert response.status_code == 200
    part = Part.objects.get(pk=shop.part.pk)
    assert part.quantity_on_hand == Decimal("5") and part.name == "Renamed"


def test_adjustments_require_a_reason_and_are_audited(shop):
    with pytest.raises(DomainError):
        inventory.adjust_stock(
            part=shop.part, counted_quantity=Decimal("3"), actor=shop.manager, reason=""
        )
    movement = inventory.adjust_stock(
        part=shop.part, counted_quantity=Decimal("3"), actor=shop.manager, reason="Cycle count"
    )
    assert movement.on_hand_delta == Decimal("-2") and movement.on_hand_after == Decimal("3")
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(action="inventory.adjusted", business=shop.business).exists()


def test_database_constraints_block_negative_stock(shop):
    with pytest.raises(IntegrityError), transaction.atomic():
        Part.objects.filter(pk=shop.part.pk).update(quantity_on_hand=Decimal("-1"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Part.objects.filter(pk=shop.part.pk).update(quantity_reserved=Decimal("6"))


def test_stock_ledger_is_append_only(shop):
    movement = StockMovement.objects.filter(part=shop.part).first()
    with pytest.raises(IntegrityError), transaction.atomic():
        StockMovement.objects.filter(pk=movement.pk).update(reason="changed")


def test_low_stock_alert_fires_once_when_crossing_threshold(shop, order):
    # Threshold is 2 and 5 are available.
    inventory.reserve(
        order=order, part=shop.part, quantity=Decimal("2"), actor=shop.manager, idempotency_key="a"
    )
    assert not Notification.objects.filter(kind=NotificationKind.LOW_STOCK).exists()
    inventory.reserve(
        order=order, part=shop.part, quantity=Decimal("1"), actor=shop.manager, idempotency_key="b"
    )
    alerts = Notification.objects.filter(kind=NotificationKind.LOW_STOCK)
    # One email each to the owner and the manager.
    assert sorted(alerts.values_list("recipient_email", flat=True)) == [
        "manager@alpha.test",
        "owner@alpha.test",
    ]
    inventory.reserve(
        order=order, part=shop.part, quantity=Decimal("1"), actor=shop.manager, idempotency_key="c"
    )
    assert alerts.count() == 2
