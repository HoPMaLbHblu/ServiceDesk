"""Domain errors and the single API error format.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "fields": {...}, "details": {...}}}

``fields`` holds field-level validation messages and ``details`` holds
structured data the interface can use, for example the conflicting appointment.
"""

import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class DomainError(exceptions.APIException):
    """A business rule refused the operation."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "business_rule_violation"
    default_detail = "The operation is not allowed."

    def __init__(
        self, message: str | None = None, *, code: str | None = None, details=None, fields=None
    ):
        self.message = message or self.default_detail
        self.error_code = code or self.default_code
        self.details = details or {}
        self.fields = fields or {}
        super().__init__(detail=self.message, code=self.error_code)


class ConflictError(DomainError):
    """The request conflicts with current state (double booking, stock, stale version)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "The request conflicts with the current state."


class InvalidTransition(ConflictError):
    default_code = "invalid_transition"
    default_detail = "This status change is not allowed."


class PlanLimitExceeded(DomainError):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_code = "plan_limit_exceeded"
    default_detail = "Your subscription does not allow this action."


class NoActiveWorkspace(exceptions.APIException):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "no_active_workspace"
    default_detail = "Select a workspace first."


def _flatten(detail):
    if isinstance(detail, list):
        return (
            [str(item) for item in detail]
            if all(not isinstance(i, dict | list) for i in detail)
            else [_flatten(i) for i in detail]
        )
    if isinstance(detail, dict):
        return {key: _flatten(value) for key, value in detail.items()}
    return [str(detail)]


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(
            exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        )
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, DomainError):
        body = {
            "code": exc.error_code,
            "message": exc.message,
            "fields": exc.fields,
            "details": exc.details,
        }
    elif isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        fields = (
            _flatten(detail) if isinstance(detail, dict) else {"non_field_errors": _flatten(detail)}
        )
        non_field = fields.get("non_field_errors") if isinstance(fields, dict) else None
        message = (
            non_field[0]
            if non_field and isinstance(non_field[0], str)
            else "Please correct the highlighted fields."
        )
        body = {"code": "validation_error", "message": message, "fields": fields, "details": {}}
    else:
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        code = getattr(exc, "default_code", "error")
        if hasattr(detail, "code") and detail.code:
            code = detail.code
        body = {"code": str(code), "message": str(detail), "fields": {}, "details": {}}
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            body["details"] = {"retry_after_seconds": int(exc.wait)}

    if response.status_code >= 500:
        logger.error("api_error", extra={"code": body["code"]})
    response.data = {"error": body}
    return response
