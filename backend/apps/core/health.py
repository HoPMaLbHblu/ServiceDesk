"""Liveness and readiness endpoints for orchestrators and the reverse proxy."""

import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # report the dependency as down, never crash the probe
        logger.warning("readiness_database_failed", extra={"error": type(exc).__name__})
        checks["database"] = "unavailable"
    try:
        cache.set("health:ready", "1", 5)
        checks["cache"] = "ok" if cache.get("health:ready") == "1" else "unavailable"
    except Exception as exc:
        logger.warning("readiness_cache_failed", extra={"error": type(exc).__name__})
        checks["cache"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": checks},
        status=200 if healthy else 503,
    )
