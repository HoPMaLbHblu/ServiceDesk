"""Customer portal API.

A portal user only sees records of customers explicitly linked to their
account through CustomerPortalAccess. Internal notes, internal timeline entries,
internal attachments, draft estimates and staff-only fields are never exposed.
"""

from django.db import transaction
from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.estimates import services as estimates
from apps.estimates.models import DecisionChannel, Estimate, EstimateStatus
from apps.estimates.serializers import DecisionSerializer, PublicEstimateSerializer
from apps.invoicing.models import Invoice, InvoiceStatus
from apps.invoicing.pdf import render_invoice
from apps.orders import services as orders
from apps.orders.models import Attachment, OrderSource, RepairOrder
from apps.orders.views import attachment_response
from apps.scheduling.models import Appointment

from .models import Device, DeviceKind
from .services import portal_customers_for


def _customers(request):
    return portal_customers_for(request.user)


def _orders(request):
    return RepairOrder.objects.filter(customer__in=_customers(request)).select_related(
        "business", "device", "customer"
    )


class PortalOrderSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    reference = serializers.CharField()
    business_name = serializers.CharField(source="business.name")
    device = serializers.CharField(source="device.__str__")
    problem_description = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField(source="get_status_display")
    payment_status = serializers.CharField()
    expected_completion_date = serializers.DateField(allow_null=True)
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class PortalEventSerializer(serializers.Serializer):
    kind = serializers.CharField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()


class PortalAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    original_name = serializers.CharField()
    content_type = serializers.CharField()
    caption = serializers.CharField()
    created_at = serializers.DateTimeField()


class PortalInvoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    reference = serializers.CharField()
    currency = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance_due = serializers.DecimalField(max_digits=12, decimal_places=2)
    issued_at = serializers.DateTimeField()
    due_date = serializers.DateField(allow_null=True)


class PortalOrderDetailSerializer(PortalOrderSerializer):
    timeline = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    estimates = serializers.SerializerMethodField()
    invoices = serializers.SerializerMethodField()

    def get_timeline(self, order) -> list[dict]:
        return PortalEventSerializer(order.events.filter(visible_to_customer=True), many=True).data

    def get_attachments(self, order) -> list[dict]:
        return PortalAttachmentSerializer(
            order.attachments.filter(visible_to_customer=True), many=True
        ).data

    def get_estimates(self, order) -> list[dict]:
        visible = order.estimates.exclude(status=EstimateStatus.DRAFT).select_related(
            "business", "order__device", "order__customer"
        )
        return PublicEstimateSerializer(visible, many=True).data

    def get_invoices(self, order) -> list[dict]:
        return PortalInvoiceSerializer(
            order.invoices.filter(status=InvoiceStatus.ISSUED), many=True
        ).data


class PortalCustomerSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    full_name = serializers.CharField()
    business_name = serializers.CharField(source="business.name")
    devices = serializers.SerializerMethodField()

    def get_devices(self, customer) -> list[dict]:
        return [{"id": str(d.public_id), "label": str(d)} for d in customer.devices.all()]


class PortalAppointmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="public_id")
    business_name = serializers.CharField(source="business.name")
    kind = serializers.CharField(source="get_kind_display")
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    status = serializers.CharField()
    timezone = serializers.CharField(source="business.timezone")


class RepairRequestSerializer(serializers.Serializer):
    customer = serializers.UUIDField()
    device = serializers.UUIDField(required=False, allow_null=True)
    device_kind = serializers.ChoiceField(choices=DeviceKind.choices, required=False)
    device_brand = serializers.CharField(max_length=80, required=False, allow_blank=True)
    device_model = serializers.CharField(max_length=120, required=False, allow_blank=True)
    device_serial_number = serializers.CharField(max_length=120, required=False, allow_blank=True)
    problem_description = serializers.CharField(max_length=4000)

    def validate(self, attrs):
        if not attrs.get("device") and not (
            attrs.get("device_brand") and attrs.get("device_model")
        ):
            raise serializers.ValidationError(
                {"device_model": ["Choose a device or describe a new one."]}
            )
        return attrs


class PortalCustomersView(APIView):
    @extend_schema(responses=PortalCustomerSerializer(many=True))
    def get(self, request):
        customers = _customers(request).select_related("business").prefetch_related("devices")
        return Response(PortalCustomerSerializer(customers, many=True).data)


class PortalOrdersView(APIView):
    @extend_schema(responses=PortalOrderSerializer(many=True))
    def get(self, request):
        return Response(
            PortalOrderSerializer(_orders(request).order_by("-created_at")[:100], many=True).data
        )

    @extend_schema(request=RepairRequestSerializer, responses={201: PortalOrderSerializer})
    @transaction.atomic
    def post(self, request):
        """Submit a repair request. Staff see it as a new order created from the portal."""
        from apps.billing.services import assert_can_write

        serializer = RepairRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        customer = (
            _customers(request)
            .filter(public_id=data["customer"])
            .select_related("business")
            .first()
        )
        if customer is None:
            raise Http404
        assert_can_write(customer.business)
        if data.get("device"):
            device = Device.objects.filter(customer=customer, public_id=data["device"]).first()
            if device is None:
                raise serializers.ValidationError({"device": ["Unknown device."]})
        else:
            device = Device.objects.create(
                business=customer.business,
                customer=customer,
                kind=data.get("device_kind") or DeviceKind.OTHER,
                brand=data["device_brand"],
                model=data["device_model"],
                serial_number=data.get("device_serial_number", ""),
            )
        order = orders.create_order(
            business=customer.business,
            customer=customer,
            device=device,
            problem_description=data["problem_description"],
            actor=request.user,
            source=OrderSource.PORTAL,
        )
        return Response(PortalOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class PortalOrderDetailView(APIView):
    @extend_schema(responses=PortalOrderDetailSerializer)
    def get(self, request, order_id):
        order = _orders(request).filter(public_id=order_id).first()
        if order is None:
            raise Http404
        return Response(PortalOrderDetailSerializer(order).data)


class PortalEstimateDecisionView(APIView):
    @extend_schema(request=DecisionSerializer, responses=PublicEstimateSerializer)
    def post(self, request, estimate_id):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        estimate = Estimate.objects.filter(
            public_id=estimate_id, order__customer__in=_customers(request)
        ).first()
        if estimate is None:
            raise Http404
        data = serializer.validated_data
        estimate = estimates.decide(
            estimate=estimate,
            approve=data["decision"] == "approve",
            channel=DecisionChannel.PORTAL,
            decided_by=request.user,
            decided_by_name=request.user.full_name,
            note=data["note"],
            expected_hash=data.get("content_hash") or None,
        )
        return Response(PublicEstimateSerializer(estimate).data)


class PortalInvoicePdfView(APIView):
    @extend_schema(responses={200: OpenApiResponse(OpenApiTypes.BINARY)})
    def get(self, request, invoice_id):
        invoice = Invoice.objects.filter(
            public_id=invoice_id,
            status=InvoiceStatus.ISSUED,
            order__customer__in=_customers(request),
        ).first()
        if invoice is None:
            raise Http404
        response = HttpResponse(render_invoice(invoice), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.reference}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response


class PortalAttachmentView(APIView):
    @extend_schema(responses={200: OpenApiResponse(OpenApiTypes.BINARY)})
    def get(self, request, order_id, attachment_id):
        attachment = Attachment.objects.filter(
            public_id=attachment_id,
            order__public_id=order_id,
            visible_to_customer=True,
            order__customer__in=_customers(request),
        ).first()
        if attachment is None:
            raise Http404
        return attachment_response(attachment)


class PortalAppointmentsView(APIView):
    @extend_schema(responses=PortalAppointmentSerializer(many=True))
    def get(self, request):
        appointments = (
            Appointment.objects.filter(customer__in=_customers(request))
            .select_related("business")
            .order_by("-starts_at")[:50]
        )
        return Response(PortalAppointmentSerializer(appointments, many=True).data)
