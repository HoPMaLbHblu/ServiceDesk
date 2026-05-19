import django_filters
from django.db.models import F
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import TenantViewMixin
from apps.core.tenancy import MANAGERS

from . import services
from .models import Invoice, Payment
from .pdf import render_invoice
from .serializers import (
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    IssueInvoiceSerializer,
    PaymentSerializer,
    RecordPaymentSerializer,
    RefundSerializer,
    VoidSerializer,
)


class InvoiceFilter(django_filters.FilterSet):
    order = django_filters.UUIDFilter(field_name="order__public_id")
    outstanding = django_filters.BooleanFilter(method="filter_outstanding")
    issued_after = django_filters.DateFilter(field_name="issued_at", lookup_expr="date__gte")
    issued_before = django_filters.DateFilter(field_name="issued_at", lookup_expr="date__lte")

    class Meta:
        model = Invoice
        fields = ["status"]

    def filter_outstanding(self, queryset, name, value):
        if value is None:
            return queryset
        outstanding = queryset.filter(status="issued", amount_paid__lt=F("total"))
        return outstanding if value else queryset.exclude(pk__in=outstanding.values("pk"))


class InvoiceViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Invoice.objects.select_related("order", "estimate", "business").prefetch_related(
        "lines", "payments__refunds", "payments__recorded_by", "payments__refund_of"
    )
    lookup_field = "public_id"
    filterset_class = InvoiceFilter
    search_fields = ["number", "order__number", "order__customer__full_name"]
    ordering_fields = ["number", "issued_at", "total", "due_date"]
    ordering = ["-issued_at"]
    role_rules = {"*": MANAGERS}

    def get_serializer_class(self):
        return InvoiceListSerializer if self.action == "list" else InvoiceDetailSerializer

    def _detail(self, invoice, code=status.HTTP_200_OK):
        return Response(
            InvoiceDetailSerializer(self.get_queryset().get(pk=invoice.pk)).data, status=code
        )

    @extend_schema(request=IssueInvoiceSerializer, responses={201: InvoiceDetailSerializer})
    def create(self, request):
        serializer = IssueInvoiceSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        invoice = services.issue_invoice(actor=request.user, **serializer.validated_data)
        return self._detail(invoice, status.HTTP_201_CREATED)

    @extend_schema(request=VoidSerializer, responses=InvoiceDetailSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, public_id=None):
        serializer = VoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = services.void_invoice(
            invoice=self.get_object(),
            reason=serializer.validated_data["reason"],
            actor=request.user,
        )
        return self._detail(invoice)

    @extend_schema(request=RecordPaymentSerializer, responses={201: PaymentSerializer})
    @action(detail=True, methods=["post"])
    def payments(self, request, public_id=None):
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.record_payment(
            invoice=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={200: OpenApiResponse(OpenApiTypes.BINARY, description="PDF document")}
    )
    @action(detail=True, methods=["get"])
    def pdf(self, request, public_id=None):
        invoice = self.get_object()
        response = HttpResponse(render_invoice(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.reference}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response


class PaymentViewSet(TenantViewMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Payment.objects.select_related(
        "invoice", "refund_of", "recorded_by"
    ).prefetch_related("refunds")
    serializer_class = PaymentSerializer
    lookup_field = "public_id"
    role_rules = {"*": MANAGERS}

    @extend_schema(request=RefundSerializer, responses={201: PaymentSerializer})
    @action(detail=True, methods=["post"])
    def refund(self, request, public_id=None):
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = services.record_refund(
            payment=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(PaymentSerializer(refund).data, status=status.HTTP_201_CREATED)
