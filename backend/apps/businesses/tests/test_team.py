import re
import threading
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.businesses.models import Invitation, Membership, Role
from apps.businesses.services import change_role, create_business
from apps.core.exceptions import ConflictError
from apps.notifications.models import Notification, NotificationKind
from conftest import PASSWORD, client_for, make_user

pytestmark = pytest.mark.django_db


def invitation_token() -> str:
    body = Notification.objects.filter(kind=NotificationKind.INVITATION).latest("created_at").body
    return re.search(r"token=([\w-]+)", body).group(1)


def test_onboarding_creates_owned_workspace_with_trial():
    user = make_user("founder@example.com")
    client = client_for(user)
    response = client.post(
        "/api/v1/workspaces/",
        {
            "name": "Fix-It Shop",
            "timezone": "America/New_York",
            "currency": "USD",
            "tax_rate": "8.25",
        },
    )
    assert response.status_code == 201, response.data
    assert response.data["active_workspace"]["role"] == "owner"
    assert response.data["active_workspace"]["timezone"] == "America/New_York"
    billing = client.get("/api/v1/billing/subscription/").data
    assert billing["status"] == "trialing" and billing["can_write"] is True
    assert len(client.get("/api/v1/business/hours/").data) == 7


def test_onboarding_rejects_unknown_timezone():
    client = client_for(make_user("tz@example.com"))
    response = client.post("/api/v1/workspaces/", {"name": "Shop", "timezone": "Mars/Olympus"})
    assert response.status_code == 400 and "timezone" in response.data["error"]["fields"]


@pytest.mark.parametrize(
    ("role", "method", "url", "expected"),
    [
        ("manager", "patch", "/api/v1/business/", 403),
        ("technician", "patch", "/api/v1/business/", 403),
        ("manager", "get", "/api/v1/members/", 403),
        ("manager", "post", "/api/v1/invitations/", 403),
        ("manager", "get", "/api/v1/reports/dashboard/", 403),
        ("manager", "get", "/api/v1/audit-log/", 403),
        ("technician", "post", "/api/v1/customers/", 403),
        ("technician", "post", "/api/v1/orders/", 403),
        ("technician", "get", "/api/v1/invoices/", 403),
        ("technician", "post", "/api/v1/parts/", 403),
        ("technician", "get", "/api/v1/notifications/", 403),
        ("technician", "post", "/api/v1/estimates/", 403),
        ("technician", "get", "/api/v1/members/staff_options/", 200),
        ("technician", "get", "/api/v1/parts/", 200),
        ("manager", "get", "/api/v1/invoices/", 200),
        ("manager", "post", "/api/v1/billing/checkout/", 403),
    ],
)
def test_role_matrix(shop, role, method, url, expected):
    client = shop.client(role)
    response = getattr(client, method)(url, {})
    assert response.status_code == expected, response.data


def test_invitation_flow_is_single_use_and_bound_to_email(shop):
    shop.upgrade()
    owner = shop.client("owner")
    response = owner.post(
        "/api/v1/invitations/", {"email": "New.Tech@Example.com", "role": "technician"}
    )
    assert response.status_code == 201, response.data
    token = invitation_token()

    preview = APIClient().post("/api/v1/invitations/preview/", {"token": token}).data
    assert preview["business_name"] == "Alpha Repairs" and preview["status"] == "pending"

    stranger = client_for(make_user("someone.else@example.com"))
    response = stranger.post("/api/v1/invitations/accept/", {"token": token})
    assert (
        response.status_code == 400
        and response.data["error"]["code"] == "invitation_email_mismatch"
    )

    invitee = make_user("new.tech@example.com", verified=False)
    client = client_for(invitee)
    response = client.post("/api/v1/invitations/accept/", {"token": token})
    assert response.status_code == 200, response.data
    assert response.data["active_workspace"]["role"] == "technician"
    invitee.refresh_from_db()
    assert invitee.is_email_verified

    response = client.post("/api/v1/invitations/accept/", {"token": token})
    assert response.status_code == 400 and response.data["error"]["code"] == "invalid_invitation"


def test_expired_and_revoked_invitations_cannot_be_used(shop):
    shop.upgrade()
    owner = shop.client("owner")
    owner.post("/api/v1/invitations/", {"email": "late@example.com", "role": "manager"})
    token = invitation_token()
    Invitation.objects.filter(email="late@example.com").update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    late = client_for(make_user("late@example.com"))
    assert (
        late.post("/api/v1/invitations/accept/", {"token": token}).data["error"]["code"]
        == "invalid_invitation"
    )

    invitation = owner.post(
        "/api/v1/invitations/", {"email": "revoked@example.com", "role": "manager"}
    ).data
    token = invitation_token()
    assert owner.post(f"/api/v1/invitations/{invitation['id']}/revoke/").status_code == 200
    revoked = client_for(make_user("revoked@example.com"))
    assert revoked.post("/api/v1/invitations/accept/", {"token": token}).status_code == 400


def test_unverified_owner_cannot_invite():
    user = make_user("unverified@example.com", verified=False)
    business = create_business(owner=user, name="Unverified Shop")
    response = client_for(user, business).post(
        "/api/v1/invitations/", {"email": "x@example.com", "role": "manager"}
    )
    assert response.status_code == 400 and response.data["error"]["code"] == "email_not_verified"


def test_last_owner_cannot_be_demoted_or_removed(shop):
    owner = shop.client("owner")
    membership = Membership.objects.get(business=shop.business, user=shop.owner)
    response = owner.post(f"/api/v1/members/{membership.pk}/change_role/", {"role": "manager"})
    assert response.status_code == 409 and response.data["error"]["code"] == "last_owner"
    response = owner.post(f"/api/v1/members/{membership.pk}/deactivate/")
    assert response.status_code == 409 and response.data["error"]["code"] == "last_owner"

    # With a second owner, the first can step down.
    second = Membership.objects.get(business=shop.business, user=shop.manager)
    assert (
        owner.post(f"/api/v1/members/{second.pk}/change_role/", {"role": "owner"}).status_code
        == 200
    )
    assert (
        owner.post(f"/api/v1/members/{membership.pk}/change_role/", {"role": "manager"}).status_code
        == 200
    )
    # The audit log recorded the role changes.
    from apps.audit.models import AuditLog

    assert (
        AuditLog.objects.filter(business=shop.business, action="member.role_changed").count() == 2
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_demotions_leave_one_owner():
    """Two owners demote each other at the same moment; exactly one request may win."""
    first = make_user("first@example.com")
    second = make_user("second@example.com")
    business = create_business(owner=first, name="Race Shop")
    Membership.objects.create(business=business, user=second, role=Role.OWNER)
    memberships = list(Membership.objects.filter(business=business).order_by("pk"))
    barrier = threading.Barrier(2)
    results = []

    def demote(membership, actor):
        try:
            barrier.wait()
            change_role(membership=membership, new_role=Role.MANAGER, actor=actor)
            results.append("ok")
        except ConflictError:
            results.append("refused")
        except Exception as exc:  # surfaced in the assertion message
            results.append(repr(exc))
        finally:
            connection.close()

    threads = [
        threading.Thread(target=demote, args=(memberships[0], second)),
        threading.Thread(target=demote, args=(memberships[1], first)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok", "refused"]
    assert (
        Membership.objects.filter(business=business, role=Role.OWNER, is_active=True).count() == 1
    )


def test_staff_limit_counts_pending_invitations(shop):
    owner = shop.client("owner")
    # Starter allows 3 staff and the shop already has 3 members.
    response = owner.post(
        "/api/v1/invitations/", {"email": "fourth@example.com", "role": "technician"}
    )
    assert response.status_code == 402
    assert response.data["error"]["code"] == "staff_limit_reached"


def test_password_login_works_for_invited_user_after_accepting(shop):
    Membership.objects.filter(business=shop.business, user=shop.technician).update(is_active=False)
    owner = shop.client("owner")
    owner.post("/api/v1/invitations/", {"email": "joiner@example.com", "role": "manager"})
    token = invitation_token()
    client = APIClient()
    client.post(
        "/api/v1/auth/register/",
        {"email": "joiner@example.com", "full_name": "Joiner", "password": PASSWORD},
    )
    assert client.post("/api/v1/invitations/accept/", {"token": token}).status_code == 200
    assert client.get("/api/v1/customers/").status_code == 200


def test_business_settings_validation(shop):
    client = shop.client("owner")
    for payload, field in [
        ({"default_labor_rate": "-5"}, "default_labor_rate"),
        ({"estimate_valid_days": 0}, "estimate_valid_days"),
    ]:
        response = client.patch("/api/v1/business/", payload)
        assert response.status_code == 400 and field in response.data["error"]["fields"]


def test_currency_is_locked_once_money_exists(shop):
    from apps.estimates import services as estimates
    from apps.orders import services as orders
    from apps.orders.models import OrderStatus

    client = shop.client("owner")
    other = "EUR" if shop.business.currency != "EUR" else "USD"
    assert client.patch("/api/v1/business/", {"currency": other}).status_code == 200
    order = orders.create_order(
        business=shop.business,
        customer=shop.customer,
        device=shop.device,
        problem_description="x",
        actor=shop.manager,
        assigned_technician=shop.technician,
    )
    orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=shop.manager)
    estimates.create_version(order=order, actor=shop.manager)
    response = client.patch("/api/v1/business/", {"currency": "GBP" if other != "GBP" else "USD"})
    assert response.status_code == 400 and "currency" in response.data["error"]["fields"]
