"""Settings for the Playwright suite.

A throwaway database, background tasks run inline, and emails are written to
files so the tests can follow the links customers would receive.
"""

import os

os.environ.setdefault("POSTGRES_DB", "servicedesk_e2e")
os.environ.setdefault("CACHE_REDIS_URL", "redis://localhost:6379/5")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5180")
os.environ.setdefault("ALLOW_DEMO_DATA", "true")
os.environ.setdefault("THROTTLE_LOGIN", "1000/min")
os.environ.setdefault("THROTTLE_PUBLIC_TOKEN", "1000/min")

from .dev import *  # noqa: E402,F403
from .dev import BASE_DIR, FRONTEND_URL  # noqa: E402

CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = os.environ.get("EMAIL_FILE_PATH", str(BASE_DIR / ".e2e-emails"))
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL, "http://127.0.0.1:5180"]
