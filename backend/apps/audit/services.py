from decimal import Decimal

from apps.core.logging import request_id_var

from .models import AuditLog


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def record(
    *, action: str, entity, business=None, actor=None, changes: dict | None = None, label: str = ""
) -> AuditLog:
    """Append an audit record. Call inside the transaction that performs the change."""
    if business is None:
        business = getattr(entity, "business", None)
    actor_label = ""
    if actor is not None and getattr(actor, "is_authenticated", False):
        actor_label = f"{actor.full_name} <{actor.email}>"
    else:
        actor = None
    return AuditLog.objects.create(
        business=business,
        actor=actor,
        actor_label=actor_label or "system",
        action=action,
        entity_type=entity._meta.label_lower
        if hasattr(entity, "_meta")
        else str(type(entity).__name__),
        entity_id=str(getattr(entity, "pk", "")),
        entity_label=(label or str(entity))[:200],
        changes=_jsonable(changes or {}),
        request_id=request_id_var.get(),
    )


def diff(instance, fields: list[str], new_values: dict) -> dict:
    """Return ``{field: [old, new]}`` for fields whose value changes."""
    changes = {}
    for field in fields:
        if field in new_values:
            old = getattr(instance, field)
            new = new_values[field]
            if old != new:
                changes[field] = [_jsonable(old), _jsonable(new)]
    return changes
