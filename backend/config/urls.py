from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import health

admin.site.site_header = "ServiceDesk platform administration"
admin.site.site_title = "ServiceDesk admin"

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("", include("apps.businesses.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.estimates.urls")),
    path("", include("apps.invoicing.urls")),
    path("", include("apps.scheduling.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.billing.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.audit.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/live", health.live, name="health-live"),
    path("api/health/ready", health.ready, name="health-ready"),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
