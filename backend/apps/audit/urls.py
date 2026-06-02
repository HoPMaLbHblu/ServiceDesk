from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("audit-log", views.AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
