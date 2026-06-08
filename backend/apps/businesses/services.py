from __future__ import annotations

from datetime import time

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.tokens import hash_token, new_opaque_token
from apps.audit.services import diff, record
from apps.core.exceptions import ConflictError, DomainError

from .models import Business, BusinessCounter, Invitation, Membership, Role

SETTINGS_FIELDS = [
    "name",
    "timezone",
    "currency",
    "tax_rate",
    "default_labor_rate",
    "estimate_valid_days",
    "email",
    "phone",
    "address",
]

DEFAULT_HOURS = {
    0: (time(9), time(18)),
    1: (time(9), time(18)),
    2: (time(9), time(18)),
    3: (time(9), time(18)),
    4: (time(9), time(18)),
    5: (time(10), time(15)),
    6: None,
}


def _unique_slug(name: str) -> str:
    base = slugify(name)[:120] or "workspace"
    slug, n = base, 2
    while Business.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


@transaction.atomic
def create_business(
    *, owner, name: str, timezone_name: str = "UTC", currency: str = "USD", tax_rate=None, **extra
) -> Business:
    from apps.billing.services import start_trial
    from apps.scheduling.models import BusinessHours

    business = Business(
        name=name,
        slug=_unique_slug(name),
        timezone=timezone_name,
        currency=currency,
        created_by=owner,
        **extra,
    )
    if tax_rate is not None:
        business.tax_rate = tax_rate
    business.full_clean()
    business.save()
    Membership.objects.create(business=business, user=owner, role=Role.OWNER)
    for name_ in ("repair_order", "invoice"):
        BusinessCounter.objects.create(business=business, name=name_)
    for weekday, hours in DEFAULT_HOURS.items():
        BusinessHours.objects.create(
            business=business,
            weekday=weekday,
            opens_at=hours[0] if hours else None,
            closes_at=hours[1] if hours else None,
            is_closed=hours is None,
        )
    start_trial(business)
    record(
        action="business.created",
        entity=business,
        business=business,
        actor=owner,
        changes={"name": name},
    )
    return business


def next_number(business, name: str) -> int:
    """Allocate the next number in a per-business sequence.

    The counter row is locked until the surrounding transaction ends, so two
    concurrent requests can never receive the same number.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_number must run inside a transaction.")
    counter = (
        BusinessCounter.objects.select_for_update().filter(business=business, name=name).first()
    )
    if counter is None:
        try:
            with transaction.atomic():
                BusinessCounter.objects.create(business=business, name=name)
        except IntegrityError:
            pass  # created concurrently; lock it below
        counter = BusinessCounter.objects.select_for_update().get(business=business, name=name)
    counter.value += 1
    counter.save(update_fields=["value"])
    return counter.value


@transaction.atomic
def update_settings(*, business: Business, actor, data: dict) -> Business:
    changes = diff(business, SETTINGS_FIELDS, data)
    for field, value in data.items():
        if field in SETTINGS_FIELDS:
            setattr(business, field, value)
    business.full_clean()
    business.save()
    if changes:
        record(
            action="business.settings_changed",
            entity=business,
            business=business,
            actor=actor,
            changes=changes,
        )
    return business


# --- Invitations ---------------------------------------------------------------


@transaction.atomic
def invite_member(*, business: Business, inviter, email: str, role: str) -> tuple[Invitation, str]:
    from apps.billing.services import assert_staff_limit
    from apps.notifications.emails import footer, link
    from apps.notifications.models import NotificationKind
    from apps.notifications.services import queue_email

    email = email.strip().lower()
    if not inviter.is_email_verified:
        raise DomainError(
            "Verify your email address before inviting team members.", code="email_not_verified"
        )
    if role not in Role.values:
        raise DomainError("Unknown role.", code="invalid_role")
    if Membership.objects.filter(
        business=business, user__email__iexact=email, is_active=True
    ).exists():
        raise ConflictError(
            "This person is already a member of the workspace.", code="already_member"
        )

    # A new invitation replaces any pending one for the same address.
    Invitation.objects.filter(
        business=business, email__iexact=email, accepted_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())
    assert_staff_limit(business)

    raw, digest = new_opaque_token()
    invitation = Invitation.objects.create(
        business=business,
        email=email,
        role=role,
        token_hash=digest,
        expires_at=timezone.now() + settings.INVITATION_MAX_AGE,
        invited_by=inviter,
    )
    queue_email(
        kind=NotificationKind.INVITATION,
        to=email,
        business=business,
        subject=f"{inviter.full_name} invited you to {business.name} on ServiceDesk",
        body=(
            f"Hello,\n\n{inviter.full_name} invited you to join {business.name} on ServiceDesk "
            f"as {Role(role).label.lower()}.\n\nAccept the invitation:\n{link(f'/invitations/accept?token={raw}')}\n\n"
            f"The link can be used once and expires in {settings.INVITATION_MAX_AGE.days} days."
            + footer(business)
        ),
        idempotency_key=f"invitation:{invitation.pk}",
        contains_secret=True,
        entity=invitation,
    )
    record(
        action="member.invited",
        entity=invitation,
        business=business,
        actor=inviter,
        changes={"email": email, "role": role},
    )
    return invitation, raw


def find_invitation(raw_token: str) -> Invitation | None:
    return (
        Invitation.objects.select_related("business")
        .filter(token_hash=hash_token(raw_token))
        .first()
    )


@transaction.atomic
def accept_invitation(*, user, raw_token: str) -> Membership:
    from apps.billing.services import assert_staff_limit

    invitation = (
        Invitation.objects.select_for_update()
        .select_related("business")
        .filter(token_hash=hash_token(raw_token))
        .first()
    )
    if invitation is None or invitation.status != "pending":
        raise DomainError(
            "This invitation is invalid, expired or already used.", code="invalid_invitation"
        )
    if invitation.email.lower() != user.email.lower():
        raise DomainError(
            f"This invitation was sent to {invitation.email}. Sign in with that address to accept it.",
            code="invitation_email_mismatch",
        )
    business = invitation.business
    membership = Membership.objects.select_for_update().filter(business=business, user=user).first()
    if membership and membership.is_active:
        raise ConflictError("You are already a member of this workspace.", code="already_member")

    # The pending invitation already counted against the limit; it becomes the membership.
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    assert_staff_limit(business, adding=1)

    if membership:
        membership.is_active = True
        membership.role = invitation.role
        membership.save(update_fields=["is_active", "role", "updated_at"])
    else:
        membership = Membership.objects.create(business=business, user=user, role=invitation.role)
    if user.email_verified_at is None:
        # Opening the emailed link proves control of the address.
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    record(
        action="member.joined",
        entity=membership,
        business=business,
        actor=user,
        changes={"role": invitation.role},
        label=user.email,
    )
    return membership


@transaction.atomic
def revoke_invitation(*, invitation: Invitation, actor) -> Invitation:
    invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
    if invitation.status != "pending":
        raise ConflictError(
            "Only pending invitations can be revoked.", code="invitation_not_pending"
        )
    invitation.revoked_at = timezone.now()
    invitation.save(update_fields=["revoked_at", "updated_at"])
    record(
        action="member.invitation_revoked",
        entity=invitation,
        business=invitation.business,
        actor=actor,
        changes={"email": invitation.email},
    )
    return invitation


# --- Roles and removal ---------------------------------------------------------


def _lock_active_owners(business_id) -> list[Membership]:
    # Every change that can reduce the number of owners locks the same rows in
    # the same order, so concurrent demotions are serialized.
    return list(
        Membership.objects.select_for_update()
        .filter(business_id=business_id, role=Role.OWNER, is_active=True)
        .order_by("pk")
    )


def _ensure_another_owner_remains(business_id, membership: Membership) -> None:
    owners = _lock_active_owners(business_id)
    if membership.role == Role.OWNER and membership.is_active and len(owners) <= 1:
        raise ConflictError(
            "A workspace needs at least one active owner. Make someone else an owner first.",
            code="last_owner",
        )


@transaction.atomic
def change_role(*, membership: Membership, new_role: str, actor) -> Membership:
    if new_role not in Role.values:
        raise DomainError("Unknown role.", code="invalid_role")
    # Lock the owner rows before the target row; taking them in the opposite
    # order lets two concurrent demotions deadlock.
    _lock_active_owners(membership.business_id)
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    if membership.role == new_role:
        return membership
    if membership.role == Role.OWNER:
        _ensure_another_owner_remains(membership.business_id, membership)
    old = membership.role
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    record(
        action="member.role_changed",
        entity=membership,
        business=membership.business,
        actor=actor,
        changes={"role": [old, new_role]},
        label=membership.user.email,
    )
    return membership


@transaction.atomic
def deactivate_member(*, membership: Membership, actor) -> Membership:
    _lock_active_owners(membership.business_id)
    membership = Membership.objects.select_for_update().get(pk=membership.pk)
    if not membership.is_active:
        return membership
    _ensure_another_owner_remains(membership.business_id, membership)
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])
    record(
        action="member.removed",
        entity=membership,
        business=membership.business,
        actor=actor,
        changes={"role": membership.role},
        label=membership.user.email,
    )
    return membership
