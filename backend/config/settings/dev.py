import os

os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-change-me")

from .base import *  # noqa: E402,F403
from .base import REST_FRAMEWORK  # noqa: E402

DEBUG = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080"]

LOGGING["formatters"]["json"] = {"()": "apps.core.logging.JsonFormatter", "pretty": True}  # noqa: F405

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
