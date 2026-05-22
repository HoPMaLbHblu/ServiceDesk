from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("parts", views.PartViewSet, basename="part")
router.register("stock-movements", views.StockMovementViewSet, basename="stock-movement")
router.register("reservations", views.ReservationViewSet, basename="reservation")

urlpatterns = router.urls
