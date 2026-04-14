from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core import health

admin.site.site_header = "ServiceDesk platform administration"
admin.site.site_title = "ServiceDesk admin"

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/live", health.live, name="health-live"),
    path("api/health/ready", health.ready, name="health-ready"),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
