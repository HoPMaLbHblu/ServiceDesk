import re

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationKind
from conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db


def test_register_logs_in_and_queues_verification_email():
    client = APIClient()
    response = client.post(
        "/api/v1/auth/register/", {"email": "New@Example.com", "full_name": "New Person", "password": PASSWORD}
    )
    assert response.status_code == 201, response.data
    assert response.data["user"]["email"] == "new@example.com"
    assert response.data["user"]["email_verified"] is False
    assert response.data["active_workspace"] is None
    assert Notification.objects.filter(kind=NotificationKind.EMAIL_VERIFICATION, recipient_email="new@example.com").exists()
    assert client.get("/api/v1/auth/session/").data["authenticated"] is True


def test_register_rejects_duplicate_email_case_insensitively():
    make_user("taken@example.com")
    response = APIClient().post("/api/v1/auth/register/", {"email": "TAKEN@example.com", "full_name": "X", "password": PASSWORD})
    assert response.status_code == 400
    assert "email" in response.data["error"]["fields"]


def test_register_validates_password_strength():
    response = APIClient().post("/api/v1/auth/register/", {"email": "a@example.com", "full_name": "A", "password": "123"})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_email_verification_token_marks_user_verified():
    client = APIClient()
    client.post("/api/v1/auth/register/", {"email": "v@example.com", "full_name": "V", "password": PASSWORD})
    body = Notification.objects.get(kind=NotificationKind.EMAIL_VERIFICATION).body
    token = re.search(r"token=(\S+)", body).group(1)
    response = APIClient().post("/api/v1/auth/verify-email/", {"token": token})
    assert response.status_code == 200
    assert response.data["email_verified"] is True
    assert APIClient().post("/api/v1/auth/verify-email/", {"token": token + "x"}).status_code == 400


def test_login_logout_and_session_restoration(shop):
    client = APIClient()
    assert client.post("/api/v1/auth/login/", {"email": "owner@alpha.test", "password": "wrong"}).status_code == 400
    response = client.post("/api/v1/auth/login/", {"email": "OWNER@alpha.test", "password": PASSWORD})
    assert response.status_code == 200
    # A user with a single workspace lands in it.
    assert response.data["active_workspace"]["name"] == "Alpha Repairs"
    assert response.data["active_workspace"]["role"] == "owner"
    assert client.get("/api/v1/orders/").status_code == 200
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert client.get("/api/v1/auth/session/").data["authenticated"] is False
    assert client.get("/api/v1/orders/").status_code == 401


def test_unauthenticated_api_requests_get_401_not_403():
    response = APIClient().get("/api/v1/customers/")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"


def test_csrf_is_enforced_for_session_requests(shop):
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(shop.owner)
    response = client.post("/api/v1/workspaces/", {"name": "Another"})
    assert response.status_code == 403
    session = client.get("/api/v1/auth/session/")
    token = session.cookies["csrftoken"].value
    response = client.post("/api/v1/workspaces/", {"name": "Another"}, HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 201


def test_password_reset_flow_and_single_use():
    user = make_user("reset@example.com")
    client = APIClient()
    # The response is identical for unknown addresses.
    assert client.post("/api/v1/auth/password-reset/", {"email": "nobody@example.com"}).status_code == 202
    assert client.post("/api/v1/auth/password-reset/", {"email": "reset@example.com"}).status_code == 202
    body = Notification.objects.get(kind=NotificationKind.PASSWORD_RESET).body
    uid, token = re.search(r"uid=([\w-]+)&token=([\w-]+)", body).groups()
    new_password = "another-strong-passphrase-42"
    response = client.post("/api/v1/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": new_password})
    assert response.status_code == 204
    user.refresh_from_db()
    assert user.check_password(new_password)
    again = client.post("/api/v1/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "yet-another-passphrase-7"})
    assert again.status_code == 400


def test_sent_one_time_links_are_blanked_after_delivery():
    from apps.notifications.tasks import deliver_notification

    make_user("secret@example.com")
    APIClient().post("/api/v1/auth/password-reset/", {"email": "secret@example.com"})
    notification = Notification.objects.get(kind=NotificationKind.PASSWORD_RESET)
    assert deliver_notification(notification.pk) == "sent"
    notification.refresh_from_db()
    assert notification.status == "sent" and notification.body == ""


def test_login_is_rate_limited(shop, monkeypatch):
    from rest_framework.throttling import SimpleRateThrottle

    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {**SimpleRateThrottle.THROTTLE_RATES, "login": "3/min"})
    cache.clear()
    client = APIClient()
    codes = [client.post("/api/v1/auth/login/", {"email": "owner@alpha.test", "password": "bad"}).status_code for _ in range(5)]
    assert codes[:3] == [400, 400, 400]
    assert codes[3] == 429
    cache.clear()


def test_change_password_requires_current_password(shop):
    client = shop.client("owner")
    response = client.post("/api/v1/auth/change-password/", {"current_password": "nope", "new_password": "fresh-passphrase-123"})
    assert response.status_code == 400
    response = client.post("/api/v1/auth/change-password/", {"current_password": PASSWORD, "new_password": "fresh-passphrase-123"})
    assert response.status_code == 204
    # The session stays valid after the change.
    assert client.get("/api/v1/auth/me/").status_code == 200
