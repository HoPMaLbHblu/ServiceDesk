from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("appointments", views.AppointmentViewSet, basename="appointment")
router.register(
    "technician-availability",
    views.TechnicianAvailabilityViewSet,
    basename="technician-availability",
)
router.register("time-off", views.TimeOffViewSet, basename="time-off")

urlpatterns = [
    path("business/hours/", views.BusinessHoursView.as_view(), name="business-hours"),
    *router.urls,
]
