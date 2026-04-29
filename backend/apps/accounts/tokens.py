import hashlib
import secrets

from django.conf import settings
from django.core import signing

_VERIFY_SALT = "accounts.email-verification"


def make_email_verification_token(user) -> str:
    return signing.dumps({"u": user.pk, "e": user.email}, salt=_VERIFY_SALT)


def read_email_verification_token(token: str) -> dict | None:
    try:
        return signing.loads(
            token, salt=_VERIFY_SALT, max_age=settings.EMAIL_VERIFICATION_MAX_AGE.total_seconds()
        )
    except signing.BadSignature:
        return None


def new_opaque_token() -> tuple[str, str]:
    """Return ``(raw_token, sha256_hex)``. Only the hash is stored."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
