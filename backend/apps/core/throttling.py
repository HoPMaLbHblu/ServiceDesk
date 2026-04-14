import hashlib

from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class ScopedThrottle(ScopedRateThrottle):
    """Scoped throttle that only counts unsafe requests (POST, PATCH, ...)."""

    def allow_request(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return super().allow_request(request, view)


class EmailScopedThrottle(SimpleRateThrottle):
    """Throttle keyed by the submitted email, so one account cannot be brute-forced from many IPs."""

    scope_attr = "throttle_scope"

    def __init__(self):
        pass

    def allow_request(self, request, view):
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope or request.method != "POST":
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        email = (
            str(request.data.get("email", "")).strip().lower() if hasattr(request, "data") else ""
        )
        if not email:
            return None
        digest = hashlib.sha256(email.encode()).hexdigest()
        return f"throttle_email_{self.scope}_{digest}"
