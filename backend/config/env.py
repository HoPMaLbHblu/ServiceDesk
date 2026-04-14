"""Small helpers for reading configuration from environment variables."""

import os

from django.core.exceptions import ImproperlyConfigured

_MISSING = object()


def env(name: str, default: object = _MISSING) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        if default is _MISSING:
            raise ImproperlyConfigured(f"Environment variable {name} is required.")
        return default  # type: ignore[return-value]
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]
