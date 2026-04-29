from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.notifications.emails import footer, link
from apps.notifications.models import NotificationKind
from apps.notifications.services import queue_email

from .models import User
from .tokens import make_email_verification_token, read_email_verification_token


@transaction.atomic
def register_user(*, email: str, password: str, full_name: str) -> User:
    user = User.objects.create_user(email=email, password=password, full_name=full_name)
    send_verification_email(user)
    return user


def send_verification_email(user: User) -> None:
    token = make_email_verification_token(user)
    url = link(f"/verify-email?token={token}")
    queue_email(
        kind=NotificationKind.EMAIL_VERIFICATION,
        to=user.email,
        user=user,
        subject="Confirm your ServiceDesk email address",
        body=(
            f"Hi {user.get_short_name()},\n\n"
            f"Please confirm your email address by opening this link:\n{url}\n\n"
            "The link is valid for 3 days. If you did not create an account, ignore this email."
            + footer()
        ),
        # A new key per request so "resend" really sends; the token itself is time-limited.
        idempotency_key=f"verify:{user.pk}:{timezone.now().timestamp()}",
        contains_secret=True,
        entity=user,
    )


def verify_email(token: str) -> User | None:
    payload = read_email_verification_token(token)
    if payload is None:
        return None
    user = User.objects.filter(pk=payload.get("u"), is_active=True).first()
    # The token is bound to the address it was sent to.
    if user is None or user.email != payload.get("e"):
        return None
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    return user


def send_password_reset(email: str) -> None:
    """Send a reset link if an active account exists. Callers always report success."""
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    queue_email(
        kind=NotificationKind.PASSWORD_RESET,
        to=user.email,
        user=user,
        subject="Reset your ServiceDesk password",
        body=(
            f"Hi {user.get_short_name()},\n\n"
            f"Use this link to choose a new password:\n{link(f'/reset-password?uid={uid}&token={token}')}\n\n"
            "If you did not request a reset, you can ignore this email; your password stays the same."
            + footer()
        ),
        idempotency_key=f"reset:{user.pk}:{timezone.now().timestamp()}",
        contains_secret=True,
        entity=user,
    )
