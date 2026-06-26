import django_filters
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import TokenSerializer
from apps.core.api import TenantModelViewSet
from apps.core.tenancy import MANAGERS, STAFF
from apps.core.throttling import ScopedThrottle

from . import services
from .models import Customer, CustomerNote, Device
from .serializers import (
    CustomerNoteSerializer,
    CustomerSerializer,
    DeviceSerializer,
    PortalAccessSerializer,
    PortalInviteSerializer,
    RevokePortalSerializer,
)

OPEN_STATUSES = [
    "new",
    "scheduled",
    "diagnosing",
    "awaiting_approval",
    "in_progress",
    "ready_for_pickup",
]


def technician_customer_filter(user) -> Q:
    return Q(orders__assigned_technician=user)


class CustomerFilter(django_filters.FilterSet):
    has_open_orders = django_filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Customer
        fields = ["is_archived"]

    def filter_open(self, queryset, name, value):
        if value is None:
            return queryset
        return (
            queryset.filter(open_order_count__gt=0)
            if value
            else queryset.filter(open_order_count=0)
        )


class CustomerViewSet(TenantModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    lookup_field = "public_id"
    http_method_names = ["get", "post", "patch", "head", "options"]
    role_rules = {
        "list": STAFF,
        "retrieve": STAFF,
        "devices": STAFF,
        "notes": STAFF,
        "*": MANAGERS,
    }
    filterset_class = CustomerFilter
    search_fields = ["full_name", "company", "email", "phone", "devices__serial_number"]
    ordering_fields = ["full_name", "created_at"]
    ordering = ["full_name"]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .annotate(
                device_count=Count("devices", distinct=True),
                open_order_count=Count(
                    "orders", filter=Q(orders__status__in=OPEN_STATUSES), distinct=True
                ),
            )
        )
        if self.tenant.is_technician:
            queryset = queryset.filter(technician_customer_filter(self.request.user))
        return queryset.distinct()

    @extend_schema(responses=DeviceSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def devices(self, request, public_id=None):
        customer = self.get_object()
        devices = Device.objects.filter(business=self.tenant.business, customer=customer)
        return Response(
            DeviceSerializer(devices, many=True, context=self.get_serializer_context()).data
        )

    @extend_schema(methods=["get"], responses=CustomerNoteSerializer(many=True))
    @extend_schema(
        methods=["post"], request=CustomerNoteSerializer, responses={201: CustomerNoteSerializer}
    )
    @action(detail=True, methods=["get", "post"], pagination_class=None)
    def notes(self, request, public_id=None):
        customer = self.get_object()
        if request.method == "POST":
            if not self.tenant.is_manager_or_owner:
                self.permission_denied(
                    request, message="Only owners and managers can add customer notes."
                )
            serializer = CustomerNoteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            note = serializer.save(
                business=self.tenant.business, customer=customer, author=request.user
            )
            return Response(CustomerNoteSerializer(note).data, status=status.HTTP_201_CREATED)
        notes = CustomerNote.objects.filter(
            business=self.tenant.business, customer=customer
        ).select_related("author")
        return Response(CustomerNoteSerializer(notes, many=True).data)

    @extend_schema(responses=PortalAccessSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def portal_access(self, request, public_id=None):
        customer = self.get_object()
        links = customer.portal_access.filter(revoked_at__isnull=True).select_related("user")
        return Response(PortalAccessSerializer(links, many=True).data)

    @extend_schema(request=PortalInviteSerializer, responses={202: None})
    @action(detail=True, methods=["post"])
    def invite_to_portal(self, request, public_id=None):
        serializer = PortalInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.invite_to_portal(
            customer=self.get_object(), email=serializer.validated_data["email"], actor=request.user
        )
        return Response(status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=RevokePortalSerializer, responses={204: None})
    @action(detail=True, methods=["post"])
    def revoke_portal(self, request, public_id=None):
        serializer = RevokePortalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.revoke_portal_access(
            customer=self.get_object(),
            access_id=serializer.validated_data["access_id"],
            actor=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceViewSet(TenantModelViewSet):
    queryset = Device.objects.select_related("customer")
    serializer_class = DeviceSerializer
    lookup_field = "public_id"
    http_method_names = ["get", "post", "patch", "head", "options"]
    role_rules = {"list": STAFF, "retrieve": STAFF, "*": MANAGERS}
    filterset_fields = {"customer__public_id": ["exact"], "kind": ["exact"]}
    search_fields = ["brand", "model", "serial_number", "imei", "customer__full_name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(orders__assigned_technician=self.request.user).distinct()
        return queryset


class PortalAcceptView(APIView):
    throttle_classes = [ScopedThrottle]
    throttle_scope = "public_token"

    @extend_schema(request=TokenSerializer, responses={204: None})
    def post(self, request):
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.accept_portal_invitation(
            user=request.user, raw_token=serializer.validated_data["token"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
