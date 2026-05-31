import csv
from datetime import timedelta

from django.http import Http404, StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.tenancy import OWNER, HasWorkspaceRole, require_tenant
from apps.customers.models import Customer
from apps.inventory.models import Part
from apps.invoicing.models import Invoice, Payment
from apps.orders.models import RepairOrder

from . import services

MAX_RANGE_DAYS = 366


class PeriodSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, attrs):
        tenant = self.context["tenant"]
        today = timezone.now().astimezone(tenant.business.tzinfo).date()
        end = attrs.get("end") or today
        start = attrs.get("start") or end - timedelta(days=29)
        if start > end:
            raise serializers.ValidationError({"start": ["Start must be on or before end."]})
        if (end - start).days > MAX_RANGE_DAYS:
            raise serializers.ValidationError({"start": [f"Choose at most {MAX_RANGE_DAYS} days."]})
        return {"start": start, "end": end}


class DashboardView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"get": OWNER}

    @extend_schema(parameters=[PeriodSerializer], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        tenant = require_tenant(request)
        period = PeriodSerializer(data=request.query_params, context={"tenant": tenant})
        period.is_valid(raise_exception=True)
        return Response(services.dashboard(tenant.business, **period.validated_data))


def _safe(value) -> str:
    """Neutralize spreadsheet formulas in exported text (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class _Echo:
    def write(self, value):
        return value


def _dataset(name, business, start_dt, end_dt):
    tz = business.tzinfo

    def local(dt):
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if dt else ""

    if name == "orders":
        yield [
            "reference",
            "created",
            "status",
            "payment_status",
            "priority",
            "customer",
            "device",
            "technician",
            "expected",
            "completed",
        ]
        for o in (
            RepairOrder.objects.filter(
                business=business, created_at__gte=start_dt, created_at__lt=end_dt
            )
            .select_related("customer", "device", "assigned_technician")
            .order_by("number")
        ):
            yield [
                o.reference,
                local(o.created_at),
                o.status,
                o.payment_status,
                o.priority,
                o.customer.full_name,
                str(o.device),
                o.assigned_technician.full_name if o.assigned_technician else "",
                o.expected_completion_date or "",
                local(o.completed_at),
            ]
    elif name == "invoices":
        yield [
            "reference",
            "issued",
            "status",
            "order",
            "customer",
            "currency",
            "subtotal",
            "tax",
            "total",
            "paid",
            "balance",
            "due",
        ]
        for i in (
            Invoice.objects.filter(business=business, issued_at__gte=start_dt, issued_at__lt=end_dt)
            .select_related("order")
            .order_by("number")
        ):
            yield [
                i.reference,
                local(i.issued_at),
                i.status,
                i.order.reference,
                i.customer_snapshot.get("name", ""),
                i.currency,
                i.subtotal,
                i.tax_total,
                i.total,
                i.amount_paid,
                i.balance_due,
                i.due_date or "",
            ]
    elif name == "payments":
        yield ["received", "kind", "method", "source", "amount", "invoice", "reference", "note"]
        for p in (
            Payment.objects.filter(
                business=business, received_at__gte=start_dt, received_at__lt=end_dt
            )
            .select_related("invoice")
            .order_by("received_at")
        ):
            yield [
                local(p.received_at),
                p.kind,
                p.method,
                p.source,
                p.amount,
                p.invoice.reference,
                p.reference,
                p.note,
            ]
    elif name == "parts":
        yield [
            "sku",
            "name",
            "unit",
            "on_hand",
            "reserved",
            "available",
            "threshold",
            "purchase_cost",
            "selling_price",
            "active",
        ]
        for p in Part.objects.filter(business=business).order_by("sku"):
            yield [
                p.sku,
                p.name,
                p.unit,
                p.quantity_on_hand,
                p.quantity_reserved,
                p.quantity_available,
                p.low_stock_threshold,
                p.purchase_cost,
                p.selling_price,
                p.is_active,
            ]
    elif name == "customers":
        yield ["name", "company", "email", "phone", "created", "archived"]
        for c in Customer.objects.filter(business=business).order_by("full_name"):
            yield [c.full_name, c.company, c.email, c.phone, local(c.created_at), c.is_archived]
    else:
        raise Http404


class ExportView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"get": OWNER}
    datasets = ["orders", "invoices", "payments", "parts", "customers"]

    @extend_schema(
        parameters=[
            PeriodSerializer,
            OpenApiParameter("dataset", str, OpenApiParameter.PATH, enum=datasets),
        ],
        responses={200: OpenApiResponse(OpenApiTypes.STR, description="CSV file")},
    )
    def get(self, request, dataset):
        tenant = require_tenant(request)
        if dataset not in self.datasets:
            raise Http404
        period = PeriodSerializer(data=request.query_params, context={"tenant": tenant})
        period.is_valid(raise_exception=True)
        start_dt, end_dt = services.period_bounds(tenant.business, **period.validated_data)
        writer = csv.writer(_Echo())
        rows = (
            writer.writerow([_safe(v) for v in row])
            for row in _dataset(dataset, tenant.business, start_dt, end_dt)
        )
        response = StreamingHttpResponse(rows, content_type="text/csv; charset=utf-8")
        stamp = f"{period.validated_data['start']}_{period.validated_data['end']}"
        response["Content-Disposition"] = (
            f'attachment; filename="{tenant.business.slug}-{dataset}-{stamp}.csv"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
