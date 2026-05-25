from datetime import timedelta

import django_filters
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.api import TenantModelViewSet, TenantViewMixin
from apps.core.tenancy import MANAGERS, OWNER, STAFF, HasWorkspaceRole, require_tenant

from . import services
from .models import Appointment, BusinessHours, TechnicianAvailability, TimeOff
from .serializers import (
    AppointmentSerializer,
    AppointmentStatusSerializer,
    AvailabilityQuerySerializer,
    BookSerializer,
    BusinessHoursSerializer,
    RescheduleSerializer,
    TechnicianAvailabilitySerializer,
    TimeOffSerializer,
)


class AppointmentFilter(django_filters.FilterSet):
    start = django_filters.IsoDateTimeFilter(field_name="ends_at", lookup_expr="gt")
    end = django_filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lt")
    technician = django_filters.UUIDFilter(field_name="technician__public_id")
    customer = django_filters.UUIDFilter(field_name="customer__public_id")
    order = django_filters.UUIDFilter(field_name="order__public_id")

    class Meta:
        model = Appointment
        fields = ["status", "kind"]


class AppointmentViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Appointment.objects.select_related("customer", "technician", "order")
    serializer_class = AppointmentSerializer
    lookup_field = "public_id"
    filterset_class = AppointmentFilter
    ordering = ["starts_at"]
    pagination_class = None
    role_rules = {"list": STAFF, "retrieve": STAFF, "availability": STAFF, "*": MANAGERS}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(technician=self.request.user)
        if self.action == "list" and not any(
            k in self.request.query_params for k in ("start", "end", "order", "customer")
        ):
            # Calendar queries are bounded; without a range, show the coming month.
            now = timezone.now()
            queryset = queryset.filter(
                ends_at__gt=now - timedelta(days=1), starts_at__lt=now + timedelta(days=31)
            )
        return queryset

    @extend_schema(request=BookSerializer, responses={201: AppointmentSerializer})
    def create(self, request):
        serializer = BookSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        appointment = services.book(
            business=self.tenant.business, actor=request.user, **serializer.validated_data
        )
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=RescheduleSerializer, responses=AppointmentSerializer)
    @action(detail=True, methods=["post"])
    def reschedule(self, request, public_id=None):
        serializer = RescheduleSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        appointment = services.reschedule(
            appointment=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(request=AppointmentStatusSerializer, responses=AppointmentSerializer)
    @action(detail=True, methods=["post"])
    def set_status(self, request, public_id=None):
        serializer = AppointmentStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = services.set_status(
            appointment=self.get_object(), actor=request.user, **serializer.validated_data
        )
        return Response(AppointmentSerializer(appointment).data)

    @extend_schema(
        parameters=[AvailabilityQuerySerializer],
        responses=serializers.ListSerializer(child=serializers.DateTimeField()),
    )
    @action(detail=False, methods=["get"])
    def availability(self, request):
        query = AvailabilityQuerySerializer(
            data=request.query_params, context=self.get_serializer_context()
        )
        query.is_valid(raise_exception=True)
        slots = services.free_slots(
            business=self.tenant.business,
            technician=query.validated_data["technician"],
            day=query.validated_data["date"],
            duration_minutes=query.validated_data["duration_minutes"],
        )
        return Response([slot.isoformat() for slot in slots])


class BusinessHoursView(APIView):
    permission_classes = [HasWorkspaceRole]
    role_rules = {"get": STAFF, "put": OWNER}

    @extend_schema(responses=BusinessHoursSerializer(many=True))
    def get(self, request):
        tenant = require_tenant(request)
        return Response(
            BusinessHoursSerializer(
                BusinessHours.objects.filter(business=tenant.business), many=True
            ).data
        )

    @extend_schema(
        request=BusinessHoursSerializer(many=True), responses=BusinessHoursSerializer(many=True)
    )
    @transaction.atomic
    def put(self, request):
        tenant = require_tenant(request)
        serializer = BusinessHoursSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        for row in serializer.validated_data:
            if row.get("is_closed"):
                row["opens_at"] = row["closes_at"] = None
            BusinessHours.objects.update_or_create(
                business=tenant.business, weekday=row["weekday"], defaults=row
            )
        record(
            action="business.hours_changed",
            entity=tenant.business,
            business=tenant.business,
            actor=request.user,
            changes={"hours": [dict(r) for r in serializer.validated_data]},
        )
        return Response(
            BusinessHoursSerializer(
                BusinessHours.objects.filter(business=tenant.business), many=True
            ).data
        )


class TechnicianAvailabilityViewSet(TenantModelViewSet):
    queryset = TechnicianAvailability.objects.select_related("technician")
    serializer_class = TechnicianAvailabilitySerializer
    filterset_fields = {"technician__public_id": ["exact"]}
    pagination_class = None
    role_rules = {"list": STAFF, "retrieve": STAFF, "*": MANAGERS}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(technician=self.request.user)
        return queryset


class TimeOffViewSet(TenantModelViewSet):
    queryset = TimeOff.objects.select_related("technician")
    serializer_class = TimeOffSerializer
    filterset_fields = {"technician__public_id": ["exact"]}
    pagination_class = None
    role_rules = {"list": STAFF, "retrieve": STAFF, "*": MANAGERS}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(technician=self.request.user)
        return queryset
