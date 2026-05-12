import django_filters
from django.db.models import Q
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.core.api import TenantViewMixin
from apps.core.tenancy import MANAGERS, STAFF

from . import services
from .models import Attachment, OrderStatus, RepairOrder
from .serializers import (
    AttachmentSerializer,
    AttachmentUploadSerializer,
    DiagnosticsSerializer,
    NoteCreateSerializer,
    OrderCreateSerializer,
    OrderDetailSerializer,
    OrderEventSerializer,
    OrderListSerializer,
    OrderUpdateSerializer,
    TransitionSerializer,
)


class OrderFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=OrderStatus.choices)
    open = django_filters.BooleanFilter(method="filter_open")
    customer = django_filters.UUIDFilter(field_name="customer__public_id")
    device = django_filters.UUIDFilter(field_name="device__public_id")
    technician = django_filters.UUIDFilter(field_name="assigned_technician__public_id")
    unassigned = django_filters.BooleanFilter(
        field_name="assigned_technician", lookup_expr="isnull"
    )
    created_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_before = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = RepairOrder
        fields = ["status", "priority", "payment_status"]

    def filter_open(self, queryset, name, value):
        closed = [OrderStatus.COMPLETED, OrderStatus.CANCELLED]
        if value is None:
            return queryset
        return queryset.exclude(status__in=closed) if value else queryset.filter(status__in=closed)


class OrderViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = RepairOrder.objects.select_related(
        "customer", "device", "assigned_technician", "diagnosed_by"
    )
    lookup_field = "public_id"
    filterset_class = OrderFilter
    search_fields = [
        "number",
        "customer__full_name",
        "customer__phone",
        "device__serial_number",
        "device__model",
        "problem_description",
    ]
    ordering_fields = [
        "number",
        "created_at",
        "updated_at",
        "expected_completion_date",
        "priority",
        "status",
    ]
    ordering = ["-created_at"]
    role_rules = {
        "create": MANAGERS,
        "partial_update": MANAGERS,
        "*": STAFF,
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(assigned_technician=self.request.user)
        query = self.request.query_params.get("search", "").strip()
        if query.upper().startswith("RO-") and query[3:].isdigit():
            queryset = queryset.filter(Q(number=int(query[3:])))
        return queryset

    def get_serializer_class(self):
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def _detail(self, order, status_code=status.HTTP_200_OK):
        return Response(
            OrderDetailSerializer(order, context=self.get_serializer_context()).data,
            status=status_code,
        )

    @extend_schema(request=OrderCreateSerializer, responses={201: OrderDetailSerializer})
    def create(self, request):
        serializer = OrderCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        order = services.create_order(
            business=self.tenant.business, actor=request.user, **serializer.validated_data
        )
        return self._detail(order, status.HTTP_201_CREATED)

    @extend_schema(request=OrderUpdateSerializer, responses=OrderDetailSerializer)
    def partial_update(self, request, public_id=None):
        serializer = OrderUpdateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        version = data.pop("version")
        order = services.update_order(
            order=self.get_object(), actor=request.user, data=data, expected_version=version
        )
        return self._detail(order)

    @extend_schema(request=TransitionSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, public_id=None):
        serializer = TransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.transition(
            order=self.get_object(),
            to_status=serializer.validated_data["to_status"],
            reason=serializer.validated_data["reason"],
            actor=request.user,
            tenant=self.tenant,
        )
        return self._detail(order)

    @extend_schema(request=DiagnosticsSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def diagnostics(self, request, public_id=None):
        serializer = DiagnosticsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = services.record_diagnostics(
            order=self.get_object(),
            findings=serializer.validated_data["findings"],
            actor=request.user,
        )
        return self._detail(order)

    @extend_schema(responses=OrderEventSerializer(many=True))
    @action(detail=True, methods=["get"])
    def timeline(self, request, public_id=None):
        order = self.get_object()
        return Response(OrderEventSerializer(order.events.all(), many=True).data)

    @extend_schema(request=NoteCreateSerializer, responses={201: OrderEventSerializer})
    @action(detail=True, methods=["post"])
    def notes(self, request, public_id=None):
        serializer = NoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = services.add_note(
            order=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(OrderEventSerializer(event).data, status=status.HTTP_201_CREATED)

    @extend_schema(methods=["get"], responses=AttachmentSerializer(many=True))
    @extend_schema(
        methods=["post"],
        request={"multipart/form-data": AttachmentUploadSerializer},
        responses={201: AttachmentSerializer},
    )
    @action(detail=True, methods=["get", "post"], parser_classes=[MultiPartParser, FormParser])
    def attachments(self, request, public_id=None):
        order = self.get_object()
        if request.method == "POST":
            serializer = AttachmentUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            attachment = services.add_attachment(
                order=order,
                upload=serializer.validated_data["file"],
                caption=serializer.validated_data["caption"],
                visible_to_customer=serializer.validated_data["visible_to_customer"],
                actor=request.user,
            )
            return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)
        return Response(
            AttachmentSerializer(order.attachments.select_related("uploaded_by"), many=True).data
        )

    @extend_schema(responses={200: OpenApiResponse(OpenApiTypes.BINARY)})
    @action(
        detail=True,
        methods=["get"],
        url_path=r"attachments/(?P<attachment_id>[0-9a-f-]{36})/download",
    )
    def download_attachment(self, request, public_id=None, attachment_id=None):
        order = self.get_object()  # scoped to the business and, for technicians, to their orders
        attachment = Attachment.objects.filter(
            business=self.tenant.business, order=order, public_id=attachment_id
        ).first()
        if attachment is None:
            from django.http import Http404

            raise Http404
        return attachment_response(attachment)


def attachment_response(attachment: Attachment) -> FileResponse:
    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=attachment.content_type == "application/pdf"
        or not attachment.content_type.startswith("image/"),
        filename=attachment.original_name,
        content_type=attachment.content_type,
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = (
        "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    )
    return response
