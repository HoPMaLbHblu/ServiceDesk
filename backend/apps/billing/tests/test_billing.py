import json
import time
from datetime import timedelta

import pytest
import stripe
from django.utils import timezone

from apps.billing import services
from apps.billing.models import BillingEvent, Plan, Subscription, SubscriptionStatus
from apps.orders.models import RepairOrder

pytestmark = pytest.mark.django_db


def stripe_event(shop, event_type, event_id="evt_1", created=None, **obj):
    return {
        "id": event_id,
        "type": event_type,
        "created": created or int(time.time()),
        "data": {"object": {"metadata": {"business_id": str(shop.business.public_id)}, **obj}},
    }


def test_expired_trial_makes_workspace_read_only(shop):
    Subscription.objects.filter(business=shop.business).update(
        trial_ends_at=timezone.now() - timedelta(minutes=1)
    )
    client = shop.client("manager")
    assert client.get("/api/v1/customers/").status_code == 200
    response = client.post("/api/v1/customers/", {"full_name": "New", "phone": "1"})
    assert response.status_code == 402 and response.data["error"]["code"] == "subscription_inactive"
    # Billing remains reachable so the owner can fix it.
    assert shop.client("owner").get("/api/v1/billing/subscription/").data["can_write"] is False


def test_past_due_grace_period(shop, settings):
    settings.BILLING_PAST_DUE_GRACE_DAYS = 7
    sub = Subscription.objects.get(business=shop.business)
    sub.status = SubscriptionStatus.PAST_DUE
    sub.past_due_since = timezone.now() - timedelta(days=3)
    sub.save()
    assert services.access_state(sub).can_write
    sub.past_due_since = timezone.now() - timedelta(days=8)
    sub.save()
    assert not services.access_state(sub).can_write


def test_monthly_order_limit_is_enforced_server_side(shop):
    Plan.objects.filter(code="starter").update(max_orders_per_month=2)
    client = shop.client("manager")
    body = {
        "customer": str(shop.customer.public_id),
        "device": str(shop.device.public_id),
        "problem_description": "x",
    }
    assert client.post("/api/v1/orders/", body).status_code == 201
    assert client.post("/api/v1/orders/", body).status_code == 201
    response = client.post("/api/v1/orders/", body)
    assert response.status_code == 402
    assert response.data["error"]["code"] == "order_limit_reached"
    assert response.data["error"]["details"] == {"limit": 2, "used": 2}
    assert RepairOrder.objects.filter(business=shop.business).count() == 2


def test_repeated_webhook_events_are_processed_once(shop):
    event = stripe_event(shop, "invoice.payment_failed", customer="cus_1")
    assert services.process_event(provider="stripe", event=event) == "processed"
    sub = Subscription.objects.get(business=shop.business)
    assert sub.status == SubscriptionStatus.PAST_DUE
    first_since = sub.past_due_since
    assert services.process_event(provider="stripe", event=event) == "duplicate"
    assert BillingEvent.objects.filter(event_id="evt_1").count() == 1
    sub.refresh_from_db()
    assert sub.past_due_since == first_since


def test_out_of_order_events_cannot_roll_state_back(shop):
    now = int(time.time())
    services.process_event(
        provider="stripe",
        event=stripe_event(
            shop,
            "customer.subscription.deleted",
            "evt_new",
            created=now,
            object="subscription",
            id="sub_1",
            status="canceled",
        ),
    )
    outcome = services.process_event(
        provider="stripe", event=stripe_event(shop, "invoice.paid", "evt_old", created=now - 60)
    )
    assert outcome == "ignored"
    assert Subscription.objects.get(business=shop.business).status == SubscriptionStatus.CANCELLED


def test_unknown_or_unmatched_events_are_ignored(shop):
    assert (
        services.process_event(
            provider="stripe",
            event={"id": "evt_x", "type": "charge.refunded", "data": {"object": {}}},
        )
        == "ignored"
    )
    event = {"id": "evt_y", "type": "invoice.paid", "data": {"object": {"customer": "cus_unknown"}}}
    assert services.process_event(provider="stripe", event=event) == "ignored"


def test_checkout_completion_activates_plan(shop):
    event = stripe_event(shop, "checkout.session.completed", customer="cus_9", subscription="sub_9")
    event["data"]["object"]["metadata"]["plan_code"] = "professional"
    services.process_event(provider="stripe", event=event)
    sub = Subscription.objects.select_related("plan").get(business=shop.business)
    assert (sub.status, sub.plan.code, sub.provider_customer_id, sub.provider_subscription_id) == (
        "active",
        "professional",
        "cus_9",
        "sub_9",
    )


class TestStripeWebhookEndpoint:
    secret = "whsec_test_secret"

    @pytest.fixture(autouse=True)
    def stripe_mode(self, settings):
        settings.BILLING_PROVIDER = "stripe"
        settings.STRIPE_SECRET_KEY = "sk_test_dummy"
        settings.STRIPE_WEBHOOK_SECRET = self.secret

    def sign(self, payload: str) -> str:
        timestamp = int(time.time())
        signature = stripe.WebhookSignature._compute_signature(
            f"{timestamp}.{payload}", self.secret
        )
        return f"t={timestamp},v1={signature}"

    def test_rejects_missing_and_invalid_signatures(self, shop, client):
        payload = json.dumps(stripe_event(shop, "invoice.payment_failed", "evt_sig"))
        url = "/api/v1/billing/webhooks/stripe/"
        assert client.post(url, payload, content_type="application/json").status_code == 400
        bad = client.post(
            url, payload, content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=deadbeef"
        )
        assert bad.status_code == 400
        assert not BillingEvent.objects.exists()

    def test_accepts_signed_event_once(self, shop, client):
        payload = json.dumps(
            stripe_event(shop, "invoice.payment_failed", "evt_signed", customer="cus_1")
        )
        url = "/api/v1/billing/webhooks/stripe/"
        first = client.post(
            url, payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=self.sign(payload)
        )
        second = client.post(
            url, payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=self.sign(payload)
        )
        assert (first.status_code, first.json()["result"]) == (200, "processed")
        assert second.json()["result"] == "duplicate"


def test_live_stripe_keys_are_refused(settings):
    from django.core.exceptions import ImproperlyConfigured

    from apps.billing.providers import StripeBillingProvider

    settings.STRIPE_SECRET_KEY = "sk_live_123"
    with pytest.raises(ImproperlyConfigured):
        StripeBillingProvider()


def test_dev_billing_mode_uses_the_event_pipeline(shop):
    client = shop.client("owner")
    state = client.post("/api/v1/billing/dev/", {"action": "activate", "plan": "business"}).data
    assert state["status"] == "active" and state["plan"]["code"] == "business"
    assert "Development billing mode" in state["provider_label"]
    state = client.post("/api/v1/billing/dev/", {"action": "payment_failed"}).data
    assert state["status"] == "past_due" and state["can_write"] is True
    state = client.post("/api/v1/billing/dev/", {"action": "cancel"}).data
    assert state["status"] == "cancelled" and state["can_write"] is False
    assert BillingEvent.objects.filter(provider="dev").count() == 3
    assert (
        shop.client("manager").post("/api/v1/billing/dev/", {"action": "activate"}).status_code
        == 403
    )
