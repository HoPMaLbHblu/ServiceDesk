import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from .base import *  # noqa: E402,F403
from .base import REST_FRAMEWORK  # noqa: E402

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_URL = "memory://"
MEDIA_ROOT = BASE_DIR / ".test-media"  # noqa: F405
BILLING_PROVIDER = "dev"
LOGGING = {"version": 1, "disable_existing_loggers": False}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    # Throttling is exercised in dedicated tests that override these rates.
    "DEFAULT_THROTTLE_RATES": {
        key: "10000/min" for key in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    },
}
