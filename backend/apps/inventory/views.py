import django_filters
from django.db import transaction
from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import TenantModelViewSet, TenantViewMixin
from apps.core.tenancy import MANAGERS, STAFF

from . import services
from .models import Part, PartReservation, StockMovement
from .serializers import (
    AdjustStockSerializer,
    PartSerializer,
    ReceiveStockSerializer,
    ReservationSerializer,
    ReserveSerializer,
    StockMovementSerializer,
)


class PartFilter(django_filters.FilterSet):
    low_stock = django_filters.BooleanFilter(method="filter_low")

    class Meta:
        model = Part
        fields = ["is_active", "unit"]

    def filter_low(self, queryset, name, value):
        if value is None:
            return queryset
        low = F("quantity_on_hand") - F("quantity_reserved")
        return (
            queryset.filter(**{"low_stock_threshold__gte": low})
            if value
            else queryset.filter(low_stock_threshold__lt=low)
        )


class PartViewSet(TenantModelViewSet):
    queryset = Part.objects.all()
    serializer_class = PartSerializer
    lookup_field = "public_id"
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_class = PartFilter
    search_fields = ["sku", "name", "description"]
    ordering_fields = ["name", "sku", "quantity_on_hand", "selling_price", "updated_at"]
    ordering = ["name"]
    role_rules = {"list": STAFF, "retrieve": STAFF, "movements": STAFF, "*": MANAGERS}

    @transaction.atomic
    def perform_create(self, serializer):
        initial = serializer.validated_data.pop("initial_quantity", None)
        part = serializer.save(business=self.tenant.business)
        if initial:
            services.receive_stock(
                part=part, quantity=initial, actor=self.request.user, reason="Opening stock"
            )
            part.refresh_from_db()

    def perform_update(self, serializer):
        serializer.validated_data.pop("initial_quantity", None)
        serializer.save()

    @extend_schema(request=ReceiveStockSerializer, responses={201: StockMovementSerializer})
    @action(detail=True, methods=["post"])
    def receive(self, request, public_id=None):
        serializer = ReceiveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = services.receive_stock(
            part=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=AdjustStockSerializer, responses={201: StockMovementSerializer})
    @action(detail=True, methods=["post"])
    def adjust(self, request, public_id=None):
        serializer = AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement = services.adjust_stock(
            part=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=StockMovementSerializer(many=True))
    @action(detail=True, methods=["get"])
    def movements(self, request, public_id=None):
        part = self.get_object()
        queryset = StockMovement.objects.filter(
            business=self.tenant.business, part=part
        ).select_related("part", "order", "actor")
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(StockMovementSerializer(page, many=True).data)


class StockMovementViewSet(TenantViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = StockMovement.objects.select_related("part", "order", "actor")
    serializer_class = StockMovementSerializer
    filterset_fields = {"kind": ["exact"], "part__public_id": ["exact"]}
    ordering = ["-created_at", "-id"]
    role_rules = {"*": MANAGERS}


class ReservationViewSet(TenantViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PartReservation.objects.select_related("part", "order")
    serializer_class = ReservationSerializer
    lookup_field = "public_id"
    filterset_fields = {"order__public_id": ["exact"], "status": ["exact"]}
    pagination_class = None
    role_rules = {"*": STAFF}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(order__assigned_technician=self.request.user)
        return queryset

    @extend_schema(
        request=ReserveSerializer,
        responses={201: ReservationSerializer, 200: ReservationSerializer},
    )
    def create(self, request):
        serializer = ReserveSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data["order"]
        if self.tenant.is_technician and order.assigned_technician_id != request.user.pk:
            from django.http import Http404

            raise Http404
        reservation, created = services.reserve(actor=request.user, **serializer.validated_data)
        return Response(
            ReservationSerializer(reservation).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(request=None, responses=ReservationSerializer)
    @action(detail=True, methods=["post"])
    def consume(self, request, public_id=None):
        reservation, _ = services.consume(reservation=self.get_object(), actor=request.user)
        return Response(ReservationSerializer(reservation).data)

    @extend_schema(request=None, responses=ReservationSerializer)
    @action(detail=True, methods=["post"])
    def release(self, request, public_id=None):
        reservation, _ = services.release(reservation=self.get_object(), actor=request.user)
        return Response(ReservationSerializer(reservation).data)
