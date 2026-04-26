"""Plain-text email content. Kept in one place so wording stays consistent."""

from django.conf import settings


def link(path: str) -> str:
    return f"{settings.FRONTEND_URL}{path}"


def footer(business=None) -> str:
    sender = business.name if business is not None else "ServiceDesk"
    return f"\n\n--\n{sender}\nSent by ServiceDesk. Please do not reply to this automated message."
