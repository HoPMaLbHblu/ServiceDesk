"""Billing providers.

``dev``: a clearly labelled development mode. Checkout opens an in-app page
that says no payment is taken; confirming it produces a synthetic event that
goes through the same ``process_event`` path as a real webhook.

``stripe``: Stripe Checkout, Billing Portal and signed webhooks, used only with
test-mode keys. Live keys are refused.
"""

from __future__ import annotations

import secrets
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.core.exceptions import DomainError


class DevBillingProvider:
    name = "dev"
    label = "Development billing mode: no real payments are taken."

    def checkout_url(self, *, subscription, plan) -> str:
        return f"{settings.FRONTEND_URL}/settings/billing/dev-checkout?plan={plan.code}"

    def portal_url(self, *, subscription) -> str:
        return f"{settings.FRONTEND_URL}/settings/billing"

    @staticmethod
    def synthetic_event(
        *, event_type: str, subscription, plan=None, status: str | None = None
    ) -> dict:
        obj = {
            "object": "checkout.session" if event_type.startswith("checkout") else "subscription",
            "id": subscription.provider_subscription_id
            or f"dev_sub_{subscription.business.public_id.hex[:12]}",
            "customer": subscription.provider_customer_id
            or f"dev_cus_{subscription.business.public_id.hex[:12]}",
            "subscription": subscription.provider_subscription_id
            or f"dev_sub_{subscription.business.public_id.hex[:12]}",
            "client_reference_id": str(subscription.business.public_id),
            "metadata": {
                "business_id": str(subscription.business.public_id),
                **({"plan_code": plan.code} if plan else {}),
            },
        }
        if status:
            obj["status"] = status
        return {
            "id": f"dev_evt_{secrets.token_hex(8)}",
            "type": event_type,
            "created": int(time.time()),
            "data": {"object": obj},
        }


class StripeBillingProvider:
    name = "stripe"
    label = "Stripe test mode"

    def __init__(self):
        key = settings.STRIPE_SECRET_KEY
        if not key:
            raise ImproperlyConfigured(
                "STRIPE_SECRET_KEY is required when BILLING_PROVIDER=stripe."
            )
        if not key.startswith(("sk_test_", "rk_test_")):
            raise ImproperlyConfigured("Only Stripe test-mode keys are allowed.")
        import stripe

        self.stripe = stripe
        self.stripe.api_key = key

    def checkout_url(self, *, subscription, plan) -> str:
        if not plan.stripe_price_id:
            raise DomainError(
                f"The {plan.name} plan has no Stripe price configured.", code="plan_not_configured"
            )
        business = subscription.business
        params = {
            "mode": "subscription",
            "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
            "client_reference_id": str(business.public_id),
            "metadata": {"business_id": str(business.public_id), "plan_code": plan.code},
            "subscription_data": {
                "metadata": {"business_id": str(business.public_id), "plan_code": plan.code}
            },
            # The redirect is only a convenience. The subscription changes when the signed webhook arrives.
            "success_url": f"{settings.FRONTEND_URL}/settings/billing?checkout=returned",
            "cancel_url": f"{settings.FRONTEND_URL}/settings/billing?checkout=cancelled",
        }
        if subscription.provider_customer_id:
            params["customer"] = subscription.provider_customer_id
        session = self.stripe.checkout.Session.create(**params)
        return session.url

    def portal_url(self, *, subscription) -> str:
        if not subscription.provider_customer_id:
            raise DomainError(
                "Start a subscription before opening the billing portal.",
                code="no_billing_customer",
            )
        session = self.stripe.billing_portal.Session.create(
            customer=subscription.provider_customer_id,
            return_url=f"{settings.FRONTEND_URL}/settings/billing",
        )
        return session.url

    def parse_webhook(self, payload: bytes, signature: str) -> dict:
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise ImproperlyConfigured(
                "STRIPE_WEBHOOK_SECRET is required to accept Stripe webhooks."
            )
        event = self.stripe.Webhook.construct_event(
            payload, signature, settings.STRIPE_WEBHOOK_SECRET
        )
        return event.to_dict() if hasattr(event, "to_dict") else dict(event)


def get_provider():
    if settings.BILLING_PROVIDER == "stripe":
        return StripeBillingProvider()
    return DevBillingProvider()
