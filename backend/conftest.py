"""Shared fixtures: two independent businesses with staff in every role."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.businesses.models import Membership, Role
from apps.businesses.services import create_business
from apps.core.tenancy import SESSION_KEY
from apps.customers.models import Customer, Device
from apps.inventory.models import Part
from apps.inventory.services import receive_stock

PASSWORD = "correct-horse-battery-staple"


def make_user(email: str, name: str = "", verified: bool = True) -> User:
    user = User.objects.create_user(
        email=email, password=PASSWORD, full_name=name or email.split("@")[0].title()
    )
    if verified:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])
    return user


def client_for(user: User, business=None) -> APIClient:
    client = APIClient()
    client.force_login(user)
    if business is not None:
        session = client.session
        session[SESSION_KEY] = business.pk
        session.save()
    return client


class Shop:
    """A business with an owner, a manager, a technician, a customer, a device and a part."""

    def __init__(self, name: str, slug: str):
        self.owner = make_user(f"owner@{slug}.test", f"{name} Owner")
        self.business = create_business(
            owner=self.owner,
            name=name,
            timezone_name="Europe/London",
            currency="USD",
            tax_rate=Decimal("10.00"),
        )
        self.manager = make_user(f"manager@{slug}.test", f"{name} Manager")
        self.technician = make_user(f"tech@{slug}.test", f"{name} Tech")
        Membership.objects.create(business=self.business, user=self.manager, role=Role.MANAGER)
        Membership.objects.create(
            business=self.business, user=self.technician, role=Role.TECHNICIAN
        )
        self.customer = Customer.objects.create(
            business=self.business,
            full_name=f"{name} Customer",
            email=f"customer@{slug}.test",
            phone="555-0100",
        )
        self.device = Device.objects.create(
            business=self.business,
            customer=self.customer,
            brand="Apple",
            model="iPhone 13",
            serial_number=f"SN-{slug}",
        )
        self.part = Part.objects.create(
            business=self.business,
            sku=f"{slug.upper()}-SCR",
            name="Screen assembly",
            purchase_cost=Decimal("40.00"),
            selling_price=Decimal("89.99"),
            low_stock_threshold=Decimal("2"),
        )
        receive_stock(part=self.part, quantity=Decimal("5"), actor=self.owner)
        self.part.refresh_from_db()

    def upgrade(self, plan_code: str = "business") -> None:
        from apps.billing.models import Plan, Subscription

        Subscription.objects.filter(business=self.business).update(plan=Plan.objects.get(code=plan_code), status="active")

    def client(self, role: str = "owner") -> APIClient:
        return client_for(getattr(self, role), self.business)


@pytest.fixture
def shop(db) -> Shop:
    return Shop("Alpha Repairs", "alpha")


@pytest.fixture
def other_shop(db) -> Shop:
    return Shop("Beta Fixers", "beta")


@pytest.fixture
def next_weekday_10am():
    """A datetime at 10:00 London time on the next Tuesday (inside default opening hours)."""
    import zoneinfo

    tz = zoneinfo.ZoneInfo("Europe/London")
    now = timezone.now().astimezone(tz)
    days = (1 - now.weekday()) % 7 or 7
    return (now + timedelta(days=days)).replace(hour=10, minute=0, second=0, microsecond=0)
