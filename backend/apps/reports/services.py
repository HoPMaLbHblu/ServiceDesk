"""Owner reports. Every query is filtered by the business passed in.

Metric definitions (also returned by the API so the interface can show them):
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.core.money import ZERO
from apps.inventory.models import MovementKind, Part, StockMovement
from apps.invoicing.models import Invoice, InvoiceStatus, Payment, PaymentKind
from apps.orders.models import OrderStatus, RepairOrder
from apps.scheduling.models import Appointment, AppointmentStatus

DEFINITIONS = {
    "collected": "Payments recorded in the period minus refunds recorded in the period, by the date the money was received. "
    "Only money actually recorded counts; issued but unpaid invoices are not included.",
    "outstanding": "Sum of unpaid balances (total minus net payments) on issued, non-void invoices as of now, "
    "regardless of the selected period. Overdue means the due date has passed.",
    "orders_by_status": "Current number of repair orders in each status, for orders created in the period.",
    "turnaround": "Time from order creation to completion, for orders completed in the period.",
    "technician_workload": "Open orders assigned to each technician now, orders they completed in the period, "
    "and booked appointment hours in the next 7 days.",
    "top_parts": "Parts consumed in repairs during the period, by quantity used. Reservations that were released are excluded.",
    "low_stock": "Active parts whose available quantity (on hand minus reserved) is at or below the low-stock threshold.",
}


def period_bounds(business, start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive local dates to an aware [start, end) range in the business timezone."""
    tz = business.tzinfo
    return datetime.combine(start, time.min, tzinfo=tz), datetime.combine(
        end + timedelta(days=1), time.min, tzinfo=tz
    )


def collected(business, start_dt, end_dt) -> dict:
    payments = Payment.objects.filter(
        business=business, received_at__gte=start_dt, received_at__lt=end_dt
    )
    tz = business.tzinfo
    by_day: dict[str, Decimal] = {}
    rows = (
        payments.annotate(day=TruncDate("received_at", tzinfo=tz))
        .values("day", "kind")
        .annotate(total=Sum("amount"))
        .order_by("day")
    )
    for row in rows:
        key = row["day"].isoformat()
        sign = Decimal(1) if row["kind"] == PaymentKind.PAYMENT else Decimal(-1)
        by_day[key] = by_day.get(key, ZERO) + sign * row["total"]
    gross = payments.filter(kind=PaymentKind.PAYMENT).aggregate(s=Sum("amount"))["s"] or ZERO
    refunds = payments.filter(kind=PaymentKind.REFUND).aggregate(s=Sum("amount"))["s"] or ZERO
    series = []
    day = start_dt.date()
    while datetime.combine(day, time.min, tzinfo=tz) < end_dt:
        series.append({"date": day.isoformat(), "amount": str(by_day.get(day.isoformat(), ZERO))})
        day += timedelta(days=1)
    return {
        "gross": str(gross),
        "refunds": str(refunds),
        "net": str(gross - refunds),
        "series": series,
    }


def outstanding(business) -> dict:
    today = timezone.now().astimezone(business.tzinfo).date()
    invoices = Invoice.objects.filter(
        business=business, status=InvoiceStatus.ISSUED, amount_paid__lt=F("total")
    )
    balance = ExpressionWrapper(
        F("total") - F("amount_paid"), output_field=Invoice._meta.get_field("total")
    )
    totals = invoices.aggregate(balance=Sum(balance), count=Count("id"))
    overdue = invoices.filter(due_date__lt=today).aggregate(balance=Sum(balance), count=Count("id"))
    return {
        "balance": str(totals["balance"] or ZERO),
        "count": totals["count"],
        "overdue_balance": str(overdue["balance"] or ZERO),
        "overdue_count": overdue["count"],
    }


def orders_by_status(business, start_dt, end_dt) -> list[dict]:
    counts = dict(
        RepairOrder.objects.filter(
            business=business, created_at__gte=start_dt, created_at__lt=end_dt
        )
        .values_list("status")
        .annotate(n=Count("id"))
    )
    return [
        {"status": value, "label": label, "count": counts.get(value, 0)}
        for value, label in OrderStatus.choices
    ]


def turnaround(business, start_dt, end_dt) -> dict:
    durations = [
        (completed - created).total_seconds() / 3600
        for created, completed in RepairOrder.objects.filter(
            business=business,
            status=OrderStatus.COMPLETED,
            completed_at__gte=start_dt,
            completed_at__lt=end_dt,
        ).values_list("created_at", "completed_at")
    ]
    if not durations:
        return {"count": 0, "average_hours": None, "median_hours": None}
    return {
        "count": len(durations),
        "average_hours": round(sum(durations) / len(durations), 1),
        "median_hours": round(statistics.median(durations), 1),
    }


def technician_workload(business, start_dt, end_dt) -> list[dict]:
    from apps.businesses.models import Membership

    now = timezone.now()
    open_statuses = [
        s for s in OrderStatus.values if s not in (OrderStatus.COMPLETED, OrderStatus.CANCELLED)
    ]
    staff = (
        Membership.objects.select_related("user")
        .filter(business=business, is_active=True)
        .order_by("user__full_name")
    )
    duration = ExpressionWrapper(F("ends_at") - F("starts_at"), output_field=DurationField())
    rows = []
    for membership in staff:
        user = membership.user
        open_count = RepairOrder.objects.filter(
            business=business, assigned_technician=user, status__in=open_statuses
        ).count()
        completed = RepairOrder.objects.filter(
            business=business,
            assigned_technician=user,
            status=OrderStatus.COMPLETED,
            completed_at__gte=start_dt,
            completed_at__lt=end_dt,
        ).count()
        booked = Appointment.objects.filter(
            business=business,
            technician=user,
            status=AppointmentStatus.SCHEDULED,
            starts_at__gte=now,
            starts_at__lt=now + timedelta(days=7),
        ).aggregate(total=Sum(duration))["total"]
        if membership.role != "technician" and not (open_count or completed or booked):
            continue
        rows.append(
            {
                "user_id": str(user.public_id),
                "name": user.full_name,
                "role": membership.role,
                "open_orders": open_count,
                "completed_in_period": completed,
                "booked_hours_next_7_days": round(booked.total_seconds() / 3600, 1)
                if booked
                else 0,
            }
        )
    return rows


def top_parts(business, start_dt, end_dt, limit: int = 10) -> list[dict]:
    rows = (
        StockMovement.objects.filter(
            business=business,
            kind=MovementKind.CONSUMPTION,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )
        .values("part__public_id", "part__sku", "part__name")
        .annotate(quantity=Sum("on_hand_delta"), orders=Count("order", distinct=True))
        .order_by("quantity")[:limit]
    )
    return [
        {
            "part_id": str(r["part__public_id"]),
            "sku": r["part__sku"],
            "name": r["part__name"],
            "quantity_used": str(-r["quantity"]),
            "orders": r["orders"],
        }
        for r in rows
    ]


def low_stock(business) -> list[dict]:
    available = F("quantity_on_hand") - F("quantity_reserved")
    parts = (
        Part.objects.filter(business=business, is_active=True)
        .filter(Q(low_stock_threshold__gte=available))
        .order_by("name")
    )
    return [
        {
            "part_id": str(p.public_id),
            "sku": p.sku,
            "name": p.name,
            "available": str(p.quantity_available),
            "threshold": str(p.low_stock_threshold),
        }
        for p in parts[:50]
    ]


def dashboard(business, start: date, end: date) -> dict:
    start_dt, end_dt = period_bounds(business, start, end)
    return {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": business.timezone,
        },
        "currency": business.currency,
        "collected": collected(business, start_dt, end_dt),
        "outstanding": outstanding(business),
        "orders_by_status": orders_by_status(business, start_dt, end_dt),
        "turnaround": turnaround(business, start_dt, end_dt),
        "technician_workload": technician_workload(business, start_dt, end_dt),
        "top_parts": top_parts(business, start_dt, end_dt),
        "low_stock": low_stock(business),
        "definitions": DEFINITIONS,
    }
