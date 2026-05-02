"""Tenant resolution and role-based permissions.

The active business is stored in the server-side session and can only be set
through the workspace switch endpoint, which checks membership. On every
request the membership is loaded again, so a removed or deactivated member
loses access immediately. A business id sent by the browser is never trusted.
"""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework import permissions

from .exceptions import NoActiveWorkspace

SESSION_KEY = "active_business_id"


@dataclass(frozen=True)
class TenantContext:
    business: object
    membership: object
    user: object

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"

    @property
    def is_manager_or_owner(self) -> bool:
        return self.role in ("owner", "manager")

    @property
    def is_technician(self) -> bool:
        return self.role == "technician"


def resolve_tenant(request) -> TenantContext | None:
    """Return the validated tenant context for this request, cached on the request."""
    cached = getattr(request, "_tenant_context", False)
    if cached is not False:
        return cached

    from apps.businesses.models import Membership

    context = None
    user = getattr(request, "user", None)
    business_id = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if user is not None and user.is_authenticated and business_id:
        membership = (
            Membership.objects.select_related("business")
            .filter(user=user, business_id=business_id, is_active=True, business__is_active=True)
            .first()
        )
        if membership is None:
            request.session.pop(SESSION_KEY, None)
        else:
            context = TenantContext(business=membership.business, membership=membership, user=user)
    request._tenant_context = context
    return context


def set_active_business(request, business) -> None:
    request.session[SESSION_KEY] = business.pk
    request._tenant_context = False


def clear_active_business(request) -> None:
    request.session.pop(SESSION_KEY, None)
    request._tenant_context = False


def require_tenant(request) -> TenantContext:
    context = resolve_tenant(request)
    if context is None:
        raise NoActiveWorkspace()
    return context


class HasWorkspaceRole(permissions.BasePermission):
    """Require an active workspace and, per action, one of the allowed roles.

    Views declare ``role_rules = {"action_name": {"owner", "manager"}, "*": {...}}``.
    Actions missing from the map fall back to ``"*"``; if that is missing too,
    every member role is allowed and object-level checks decide.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view) -> bool:
        if not (request.user and request.user.is_authenticated):
            return False
        context = require_tenant(request)
        rules = getattr(view, "role_rules", {})
        action = getattr(view, "action", None) or request.method.lower()
        allowed = rules.get(action, rules.get("*"))
        return allowed is None or context.role in allowed


class SubscriptionAllowsWrites(permissions.BasePermission):
    """Read-only access once a trial ends, a subscription is cancelled or the
    past-due grace period runs out. Billing endpoints do not use this check."""

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True
        context = resolve_tenant(request)
        if context is None:
            return True  # HasWorkspaceRole reports the missing workspace
        from apps.billing.services import assert_can_write

        assert_can_write(context.business)
        return True


OWNER = frozenset({"owner"})
MANAGERS = frozenset({"owner", "manager"})
STAFF = frozenset({"owner", "manager", "technician"})
