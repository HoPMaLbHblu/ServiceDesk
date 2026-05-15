from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("estimates", views.EstimateViewSet, basename="estimate")

urlpatterns = [
    path(
        "public/approvals/<str:token>/", views.PublicApprovalView.as_view(), name="public-approval"
    ),
    *router.urls,
]
