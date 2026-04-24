from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import PublicIdModel, TenantModel

QTY = {"max_digits": 12, "decimal_places": 2}
MONEY = {"max_digits": 12, "decimal_places": 2}


class Unit(models.TextChoices):
    PIECE = "piece", "Piece"
    SET = "set", "Set"
    METER = "meter", "Meter"
    MILLILITER = "ml", "Milliliter"
    GRAM = "gram", "Gram"


class Part(PublicIdModel, TenantModel):
    """Catalog item with its stock level.

    Stock columns change only through ``inventory.services`` which writes a
    StockMovement for every change. CHECK constraints keep stock non-negative
    and stop reservations from exceeding what is on hand.
    """

    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    purchase_cost = models.DecimalField(**MONEY, default=Decimal("0.00"))
    selling_price = models.DecimalField(**MONEY, default=Decimal("0.00"))
    low_stock_threshold = models.DecimalField(**QTY, default=Decimal("0"))
    quantity_on_hand = models.DecimalField(**QTY, default=Decimal("0"))
    quantity_reserved = models.DecimalField(**QTY, default=Decimal("0"))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "sku"], name="part_sku_unique_per_business"
            ),
            models.CheckConstraint(
                condition=Q(quantity_on_hand__gte=0), name="part_on_hand_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__gte=0), name="part_reserved_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(quantity_reserved__lte=F("quantity_on_hand")),
                name="part_reserved_within_on_hand",
            ),
            models.CheckConstraint(
                condition=Q(purchase_cost__gte=0, selling_price__gte=0),
                name="part_prices_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(low_stock_threshold__gte=0), name="part_threshold_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} {self.name}"

    @property
    def quantity_available(self) -> Decimal:
        return self.quantity_on_hand - self.quantity_reserved

    @property
    def is_low_stock(self) -> bool:
        return self.quantity_available <= self.low_stock_threshold


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Reserved"
    CONSUMED = "consumed", "Consumed"
    RELEASED = "released", "Released"


class PartReservation(PublicIdModel, TenantModel):
    order = models.ForeignKey(
        "orders.RepairOrder", on_delete=models.CASCADE, related_name="reservations"
    )
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.DecimalField(**QTY)
    status = models.CharField(
        max_length=10, choices=ReservationStatus.choices, default=ReservationStatus.ACTIVE
    )
    # Client-supplied key that makes a retried "reserve" request return the first result.
    idempotency_key = models.CharField(max_length=80)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    consumed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "idempotency_key"], name="reservation_idempotency_unique"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="reservation_quantity_positive"
            ),
        ]


class MovementKind(models.TextChoices):
    RECEIPT = "receipt", "Stock received"
    ADJUSTMENT = "adjustment", "Manual adjustment"
    RESERVATION = "reservation", "Reserved for order"
    RELEASE = "release", "Reservation released"
    CONSUMPTION = "consumption", "Used in repair"


class StockMovement(TenantModel):
    """Immutable stock ledger entry. Database triggers block updates and deletes."""

    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name="movements")
    kind = models.CharField(max_length=20, choices=MovementKind.choices)
    on_hand_delta = models.DecimalField(**QTY, default=Decimal("0"))
    reserved_delta = models.DecimalField(**QTY, default=Decimal("0"))
    on_hand_after = models.DecimalField(**QTY)
    reserved_after = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(**MONEY, null=True, blank=True)
    order = models.ForeignKey(
        "orders.RepairOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reservation = models.ForeignKey(
        PartReservation, null=True, blank=True, on_delete=models.SET_NULL, related_name="movements"
    )
    reason = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    idempotency_key = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["business", "part", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="movement_idempotency_unique",
            ),
        ]
