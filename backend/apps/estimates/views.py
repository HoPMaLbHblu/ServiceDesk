from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api import TenantViewMixin
from apps.core.exceptions import DomainError
from apps.core.tenancy import MANAGERS, STAFF
from apps.core.throttling import ScopedThrottle

from . import services
from .models import DecisionChannel, Estimate
from .serializers import (
    EstimateCreateSerializer,
    EstimateSerializer,
    PublicDecisionSerializer,
    PublicEstimateSerializer,
    ReplaceLinesSerializer,
    StaffDecisionSerializer,
)


class EstimateViewSet(
    TenantViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Estimate.objects.select_related("order").prefetch_related("lines__part")
    serializer_class = EstimateSerializer
    lookup_field = "public_id"
    filterset_fields = {"order__public_id": ["exact"], "status": ["exact"]}
    pagination_class = None
    role_rules = {"list": STAFF, "retrieve": STAFF, "*": MANAGERS}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.tenant.is_technician:
            queryset = queryset.filter(order__assigned_technician=self.request.user)
        return queryset

    def _out(self, estimate, code=status.HTTP_200_OK):
        estimate = self.get_queryset().get(pk=estimate.pk)
        return Response(EstimateSerializer(estimate).data, status=code)

    @extend_schema(request=EstimateCreateSerializer, responses={201: EstimateSerializer})
    def create(self, request):
        serializer = EstimateCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        estimate = services.create_version(
            order=serializer.validated_data["order"], actor=request.user
        )
        return self._out(estimate, status.HTTP_201_CREATED)

    @extend_schema(request=ReplaceLinesSerializer, responses=EstimateSerializer)
    @action(detail=True, methods=["post"])
    def lines(self, request, public_id=None):
        serializer = ReplaceLinesSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        estimate = services.replace_lines(
            estimate=self.get_object(),
            lines=serializer.validated_data["lines"],
            notes=serializer.validated_data.get("notes"),
            actor=request.user,
        )
        return self._out(estimate)

    @extend_schema(request=None, responses=EstimateSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request, public_id=None):
        estimate, _raw = services.send(estimate=self.get_object(), actor=request.user)
        return self._out(estimate)

    @extend_schema(request=StaffDecisionSerializer, responses=EstimateSerializer)
    @action(detail=True, methods=["post"])
    def record_decision(self, request, public_id=None):
        """Record a decision the customer gave in person or by phone."""
        serializer = StaffDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        estimate = services.decide(
            estimate=self.get_object(),
            approve=data["decision"] == "approve",
            channel=DecisionChannel.STAFF,
            decided_by=request.user,
            decided_by_name=data["customer_name"],
            note=data["note"],
            expected_hash=data.get("content_hash") or None,
        )
        return self._out(estimate)


class PublicApprovalView(APIView):
    """Approval page reached from the emailed link. The token only grants this one estimate version."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedThrottle]
    throttle_scope = "public_token"

    def _link(self, token):
        approval_link = services.find_link(token)
        if approval_link is None:
            raise DomainError("This approval link is invalid.", code="invalid_token")
        return approval_link

    @extend_schema(
        parameters=[OpenApiParameter("token", str, OpenApiParameter.PATH)],
        responses=PublicEstimateSerializer,
    )
    def get(self, request, token):
        approval_link = self._link(token)
        data = PublicEstimateSerializer(approval_link.estimate).data
        data["link_state"] = services.link_state(approval_link)
        return Response(data)

    @extend_schema(request=PublicDecisionSerializer, responses=PublicEstimateSerializer)
    def post(self, request, token):
        serializer = PublicDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approval_link = self._link(token)
        state = services.link_state(approval_link)
        if state != "open":
            raise DomainError(
                "This approval link has already been used."
                if state == "used"
                else "This approval link has expired.",
                code=f"link_{state}",
            )
        data = serializer.validated_data
        estimate = services.decide(
            estimate=approval_link.estimate,
            approve=data["decision"] == "approve",
            channel=DecisionChannel.LINK,
            decided_by_name=data["name"],
            note=data["note"],
            expected_hash=data.get("content_hash") or None,
        )
        out = PublicEstimateSerializer(estimate).data
        out["link_state"] = "used"
        return Response(out)
