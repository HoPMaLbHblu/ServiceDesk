from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.tokens import hash_token, new_opaque_token
from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError

from .models import Customer, CustomerPortalAccess, PortalInvitation

PORTAL_INVITATION_DAYS = 14


@transaction.atomic
def invite_to_portal(*, customer: Customer, email: str, actor) -> PortalInvitation:
    from apps.notifications.emails import footer, link
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    email = email.strip().lower()
    PortalInvitation.objects.filter(
        customer=customer, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())
    raw, digest = new_opaque_token()
    invitation = PortalInvitation.objects.create(
        customer=customer,
        email=email,
        token_hash=digest,
        expires_at=timezone.now() + timedelta(days=PORTAL_INVITATION_DAYS),
        invited_by=actor,
    )
    business = customer.business
    queue_email(
        kind=NotificationKind.PORTAL_ACCESS,
        to=email,
        business=business,
        subject=f"Track your repairs with {business.name}",
        body=(
            f"Hello {customer.full_name},\n\n{business.name} gave you access to their customer portal, "
            "where you can follow your repairs, review estimates and see invoices.\n\n"
            f"Set up access:\n{link(f'/portal/accept?token={raw}')}\n\n"
            f"The link can be used once and expires in {PORTAL_INVITATION_DAYS} days."
            + footer(business)
        ),
        idempotency_key=f"portal-invitation:{invitation.pk}",
        contains_secret=True,
        entity=invitation,
    )
    record(action="customer.portal_invited", entity=customer, actor=actor, changes={"email": email})
    return invitation


def find_portal_invitation(raw: str) -> PortalInvitation | None:
    return (
        PortalInvitation.objects.select_related("customer__business")
        .filter(token_hash=hash_token(raw))
        .first()
    )


@transaction.atomic
def accept_portal_invitation(*, user, raw_token: str) -> CustomerPortalAccess:
    invitation = (
        PortalInvitation.objects.select_for_update()
        .select_related("customer__business")
        .filter(token_hash=hash_token(raw_token))
        .first()
    )
    now = timezone.now()
    if (
        invitation is None
        or invitation.accepted_at
        or invitation.revoked_at
        or invitation.expires_at <= now
    ):
        raise DomainError(
            "This portal link is invalid, expired or already used.", code="invalid_invitation"
        )
    if invitation.email.lower() != user.email.lower():
        raise DomainError(
            f"This link was sent to {invitation.email}. Sign in with that address to accept it.",
            code="invitation_email_mismatch",
        )
    invitation.accepted_at = now
    invitation.save(update_fields=["accepted_at", "updated_at"])
    access, _created = CustomerPortalAccess.objects.get_or_create(
        customer=invitation.customer,
        user=user,
        revoked_at=None,
        defaults={"granted_by": invitation.invited_by},
    )
    if user.email_verified_at is None:
        user.email_verified_at = now
        user.save(update_fields=["email_verified_at"])
    record(
        action="customer.portal_linked",
        entity=invitation.customer,
        actor=user,
        changes={"user": user.email},
    )
    return access


@transaction.atomic
def revoke_portal_access(*, customer: Customer, access_id: int, actor) -> None:
    access = (
        CustomerPortalAccess.objects.select_for_update()
        .filter(customer=customer, pk=access_id, revoked_at__isnull=True)
        .first()
    )
    if access is None:
        raise ConflictError("This portal access is not active.", code="portal_access_not_active")
    access.revoked_at = timezone.now()
    access.save(update_fields=["revoked_at", "updated_at"])
    record(
        action="customer.portal_revoked",
        entity=customer,
        actor=actor,
        changes={"user": access.user.email},
    )


def portal_customers_for(user):
    """Customer records a user may see in the portal."""
    return Customer.objects.filter(
        portal_access__user=user,
        portal_access__revoked_at__isnull=True,
        business__is_active=True,
    ).distinct()
