from django.urls import path
from rest_framework.routers import SimpleRouter

from . import portal_views, views

router = SimpleRouter()
router.register("customers", views.CustomerViewSet, basename="customer")
router.register("devices", views.DeviceViewSet, basename="device")

urlpatterns = [
    path("portal/accept/", views.PortalAcceptView.as_view(), name="portal-accept"),
    path("portal/customers/", portal_views.PortalCustomersView.as_view(), name="portal-customers"),
    path("portal/orders/", portal_views.PortalOrdersView.as_view(), name="portal-orders"),
    path(
        "portal/orders/<uuid:order_id>/",
        portal_views.PortalOrderDetailView.as_view(),
        name="portal-order",
    ),
    path(
        "portal/orders/<uuid:order_id>/attachments/<uuid:attachment_id>/download/",
        portal_views.PortalAttachmentView.as_view(),
        name="portal-attachment",
    ),
    path(
        "portal/estimates/<uuid:estimate_id>/decision/",
        portal_views.PortalEstimateDecisionView.as_view(),
        name="portal-estimate-decision",
    ),
    path(
        "portal/invoices/<uuid:invoice_id>/pdf/",
        portal_views.PortalInvoicePdfView.as_view(),
        name="portal-invoice-pdf",
    ),
    path(
        "portal/appointments/",
        portal_views.PortalAppointmentsView.as_view(),
        name="portal-appointments",
    ),
    *router.urls,
]
