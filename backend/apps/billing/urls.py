from django.urls import path

from . import views

urlpatterns = [
    path("billing/subscription/", views.SubscriptionView.as_view(), name="billing-subscription"),
    path("billing/checkout/", views.CheckoutView.as_view(), name="billing-checkout"),
    path("billing/portal/", views.PortalView.as_view(), name="billing-portal"),
    path("billing/dev/", views.DevBillingView.as_view(), name="billing-dev"),
    path(
        "billing/webhooks/stripe/", views.StripeWebhookView.as_view(), name="billing-stripe-webhook"
    ),
]
