import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.businesses.models import Business, Membership
from apps.invoicing.models import Invoice
from apps.orders.models import RepairOrder

pytestmark = pytest.mark.django_db


def test_demo_data_is_created_once(settings):
    settings.ALLOW_DEMO_DATA = True
    call_command("seed_demo")
    counts = (Business.objects.count(), RepairOrder.objects.count(), Invoice.objects.count())
    call_command("seed_demo")
    assert (
        Business.objects.count(),
        RepairOrder.objects.count(),
        Invoice.objects.count(),
    ) == counts
    assert set(Business.objects.values_list("is_demo", flat=True)) == {True}
    roles = set(Membership.objects.values_list("role", flat=True))
    assert roles == {"owner", "manager", "technician"}
    statuses = set(RepairOrder.objects.values_list("status", flat=True))
    assert {
        "completed",
        "awaiting_approval",
        "in_progress",
        "ready_for_pickup",
        "cancelled",
    } <= statuses


def test_demo_data_is_refused_in_production(settings):
    settings.DEBUG = False
    settings.ALLOW_DEMO_DATA = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
