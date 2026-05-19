from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("payments", views.PaymentViewSet, basename="payment")

urlpatterns = router.urls
