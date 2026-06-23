import pytest
from django.db import IntegrityError, transaction

from apps.audit.models import AuditLog
from apps.audit.services import record

pytestmark = pytest.mark.django_db


def test_audit_records_are_append_only(shop):
    entry = record(
        action="test.action",
        entity=shop.business,
        business=shop.business,
        actor=shop.owner,
        changes={"a": 1},
    )
    assert entry.actor_label == f"{shop.owner.full_name} <{shop.owner.email}>"
    with pytest.raises(RuntimeError):
        entry.save()
    with pytest.raises(RuntimeError):
        entry.delete()
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).update(action="tampered")
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_settings_changes_are_audited_with_diff(shop):
    response = shop.client("owner").patch(
        "/api/v1/business/", {"tax_rate": "7.50", "name": "Alpha Repairs"}
    )
    assert response.status_code == 200
    log = AuditLog.objects.get(action="business.settings_changed")
    assert log.changes == {"tax_rate": ["10.00", "7.50"]}


def test_no_api_can_modify_audit_records(shop):
    client = shop.client("owner")
    entry_id = client.get("/api/v1/audit-log/").data["results"][0]["id"]
    assert client.patch(f"/api/v1/audit-log/{entry_id}/", {"action": "x"}).status_code in (404, 405)
    assert client.delete(f"/api/v1/audit-log/{entry_id}/").status_code in (404, 405)
