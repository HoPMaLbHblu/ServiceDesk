"""Create two demo workspaces with realistic data and one account per role.

Idempotent: a workspace that already exists is left untouched, so running the
command again never duplicates records. Demo workspaces are flagged ``is_demo``.
Everything is created through the same services the API uses, so the data obeys
the same rules (stock ledger, order workflow, totals, audit log).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import Plan, Subscription
from apps.businesses.models import Business, Membership, Role
from apps.businesses.services import create_business
from apps.customers.models import Customer, CustomerPortalAccess, Device
from apps.estimates import services as estimates
from apps.inventory import services as inventory
from apps.inventory.models import Part
from apps.invoicing import services as invoicing
from apps.orders import services as orders
from apps.orders.models import OrderSource, OrderStatus
from apps.scheduling import services as scheduling

PASSWORD = "demo-pass-2024!"

ACCOUNTS = {
    "owner": ("owner@demo.servicedesk.test", "Olivia Owner"),
    "manager": ("manager@demo.servicedesk.test", "Mark Manager"),
    "technician": ("tech@demo.servicedesk.test", "Tara Technician"),
    "technician2": ("tech2@demo.servicedesk.test", "Theo Fixwell"),
    "customer": ("customer@demo.servicedesk.test", "Chris Customer"),
    "owner_b": ("owner.b@demo.servicedesk.test", "Bianca Brooks"),
}

PARTS = [
    ("SCR-IP13", "iPhone 13 screen (OLED)", "89.00", "149.00", 6, 2),
    ("BAT-IP12", "iPhone 12 battery", "18.00", "49.00", 10, 3),
    ("BAT-SGS21", "Galaxy S21 battery", "16.50", "45.00", 2, 2),
    ("PORT-USBC", "USB-C charging port flex", "6.00", "29.00", 12, 4),
    ("SSD-512", "NVMe SSD 512 GB", "38.00", "79.00", 4, 1),
    ("KB-MBA13", "MacBook Air 13 keyboard", "55.00", "129.00", 1, 1),
    ("PASTE-TH", "Thermal paste (syringe)", "4.00", "12.00", 8, 2),
]


class Command(BaseCommand):
    help = "Create demo workspaces, accounts and sample data (safe to run repeatedly)."

    def handle(self, *args, **options):
        if not settings.DEBUG and not getattr(settings, "ALLOW_DEMO_DATA", False):
            raise CommandError("Demo data is disabled here. Set ALLOW_DEMO_DATA=true to allow it.")
        users = {key: self._user(email, name) for key, (email, name) in ACCOUNTS.items()}
        alpha = self._alpha(users)
        self._beta(users)
        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write(f"Password for every demo account: {PASSWORD}")
        for key, (email, _) in ACCOUNTS.items():
            self.stdout.write(f"  {key:<12} {email}")
        self.stdout.write(f"Main demo workspace: {alpha.name}")

    # --- helpers -------------------------------------------------------------

    def _user(self, email: str, name: str) -> User:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email=email, password=PASSWORD, full_name=name)
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        return user

    def _activate(self, business: Business, plan_code: str) -> None:
        Subscription.objects.filter(business=business).update(
            plan=Plan.objects.get(code=plan_code),
            status="active",
            provider="dev",
            trial_ends_at=None,
            current_period_end=timezone.now() + timedelta(days=30),
        )

    @staticmethod
    def _next_weekday(tz: ZoneInfo, days_ahead: int, hour: int) -> datetime:
        day = timezone.now().astimezone(tz).date() + timedelta(days=days_ahead)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        return datetime.combine(day, time(hour), tzinfo=tz)

    # --- workspaces ----------------------------------------------------------

    @transaction.atomic
    def _alpha(self, users) -> Business:
        existing = Business.objects.filter(is_demo=True, name="Fix-It Electronics").first()
        if existing:
            self.stdout.write("Fix-It Electronics already exists; skipped.")
            return existing
        owner, manager = users["owner"], users["manager"]
        tech, tech2 = users["technician"], users["technician2"]
        business = create_business(
            owner=owner,
            name="Fix-It Electronics",
            timezone_name="Europe/London",
            currency="GBP",
            tax_rate=Decimal("20.00"),
            is_demo=True,
            default_labor_rate=Decimal("45.00"),
            phone="+44 20 7946 0000",
            email="hello@fixit.example",
            address="12 Market Street\nLondon EC1A 1AA",
        )
        self._activate(business, "professional")
        for user, role in (
            (manager, Role.MANAGER),
            (tech, Role.TECHNICIAN),
            (tech2, Role.TECHNICIAN),
        ):
            Membership.objects.create(business=business, user=user, role=role)

        parts = {}
        for sku, name, cost, price, qty, threshold in PARTS:
            part = Part.objects.create(
                business=business,
                sku=sku,
                name=name,
                purchase_cost=Decimal(cost),
                selling_price=Decimal(price),
                low_stock_threshold=Decimal(threshold),
            )
            inventory.receive_stock(
                part=part, quantity=Decimal(qty), actor=manager, reason="Opening stock"
            )
            parts[sku] = part

        def customer(name, phone, email="", **devices):
            c = Customer.objects.create(business=business, full_name=name, phone=phone, email=email)
            return c, [
                Device.objects.create(
                    business=business,
                    customer=c,
                    kind=kind,
                    brand=brand,
                    model=model,
                    serial_number=serial,
                )
                for kind, brand, model, serial in devices.get("items", [])
            ]

        chris, (chris_phone, chris_laptop) = customer(
            "Chris Customer",
            "+44 7700 900001",
            users["customer"].email,
            items=[
                ("phone", "Apple", "iPhone 13", "F2LXK1Q0P3"),
                ("laptop", "Apple", "MacBook Air 13 (2020)", "C02DJ1ABQ6L4"),
            ],
        )
        CustomerPortalAccess.objects.create(
            customer=chris, user=users["customer"], granted_by=owner
        )
        amira, (amira_phone,) = customer(
            "Amira Hassan",
            "+44 7700 900002",
            "amira@example.com",
            items=[("phone", "Samsung", "Galaxy S21", "R58R31ABCDE")],
        )
        _, (jon_phone,) = customer(
            "Jon Peters", "+44 7700 900003", items=[("phone", "Apple", "iPhone 12", "DNPXK2JZQ1")]
        )
        _, (lena_laptop,) = customer(
            "Lena Novak",
            "+44 7700 900004",
            "lena@example.com",
            items=[("laptop", "Dell", "XPS 13 9310", "7XK2Q73")],
        )
        sam, (sam_console,) = customer(
            "Sam O'Brien",
            "+44 7700 900005",
            items=[("console", "Sony", "PlayStation 5", "CFI-1216A")],
        )
        for name, phone in (
            ("Priya Shah", "+44 7700 900006"),
            ("Tom Fischer", "+44 7700 900007"),
            ("Grace Lee", "+44 7700 900008"),
        ):
            Customer.objects.create(business=business, full_name=name, phone=phone)

        tz = ZoneInfo(business.timezone)
        today = timezone.now().astimezone(tz).date()

        # 1. Completed and paid: screen replacement for Jon.
        o1 = orders.create_order(
            business=business,
            customer=jon_phone.customer,
            device=jon_phone,
            problem_description="Dropped phone, screen cracked and touch unresponsive in the top half.",
            actor=manager,
            assigned_technician=tech,
        )
        self._repair(
            o1,
            tech,
            manager,
            [("part", parts["SCR-IP13"], "1"), ("labor", None, "0.75")],
            decide="approve",
        )
        inventory_res, _ = inventory.reserve(
            order=o1,
            part=parts["SCR-IP13"],
            quantity=Decimal("1"),
            actor=tech,
            idempotency_key=f"demo-{o1.pk}-scr",
        )
        inventory.consume(reservation=inventory_res, actor=tech)
        orders.transition(order=o1, to_status=OrderStatus.READY_FOR_PICKUP, actor=tech)
        invoice = invoicing.issue_invoice(order=o1, actor=manager)
        invoicing.record_payment(
            invoice=invoice,
            amount=invoice.total,
            method="card",
            actor=manager,
            idempotency_key=f"demo-{o1.pk}-pay",
        )
        orders.transition(order=o1, to_status=OrderStatus.COMPLETED, actor=manager)

        # 2. Waiting for Chris to approve (visible in the portal).
        o2 = orders.create_order(
            business=business,
            customer=chris,
            device=chris_phone,
            problem_description="Battery drains from 100% to 20% in two hours. Phone gets warm.",
            actor=manager,
            assigned_technician=tech,
            expected_completion_date=today + timedelta(days=3),
        )
        orders.transition(order=o2, to_status=OrderStatus.DIAGNOSING, actor=tech)
        orders.record_diagnostics(
            order=o2,
            findings="Battery health 71%. Charging port clean. Recommend battery replacement.",
            actor=tech,
        )
        est = estimates.create_version(order=o2, actor=manager)
        estimates.replace_lines(
            estimate=est,
            lines=[
                {"part": parts["BAT-IP12"], "quantity": Decimal("1")},
                {
                    "kind": "labor",
                    "description": "Battery replacement",
                    "quantity": Decimal("0.5"),
                    "unit_price": Decimal("45.00"),
                },
            ],
            notes="Includes a 6-month warranty on the battery.",
            actor=manager,
        )
        estimates.send(estimate=est, actor=manager)

        # 3. In progress with a part reserved, partially paid invoice later.
        o3 = orders.create_order(
            business=business,
            customer=amira,
            device=amira_phone,
            problem_description="Not charging. Cable works with other phones.",
            actor=manager,
            assigned_technician=tech2,
            priority="high",
            expected_completion_date=today + timedelta(days=1),
        )
        self._repair(
            o3,
            tech2,
            manager,
            [("part", parts["PORT-USBC"], "1"), ("labor", None, "1")],
            decide="approve",
        )
        inventory.reserve(
            order=o3,
            part=parts["PORT-USBC"],
            quantity=Decimal("1"),
            actor=tech2,
            idempotency_key=f"demo-{o3.pk}-port",
        )

        # 4. Ready for pickup, deposit paid.
        o4 = orders.create_order(
            business=business,
            customer=lena_laptop.customer,
            device=lena_laptop,
            problem_description="Very slow, fans loud. Wants SSD upgrade and clean.",
            actor=manager,
            assigned_technician=tech,
        )
        self._repair(
            o4,
            tech,
            manager,
            [
                ("part", parts["SSD-512"], "1"),
                ("part", parts["PASTE-TH"], "1"),
                ("labor", None, "1.5"),
            ],
            decide="approve",
        )
        for sku in ("SSD-512", "PASTE-TH"):
            res, _ = inventory.reserve(
                order=o4,
                part=parts[sku],
                quantity=Decimal("1"),
                actor=tech,
                idempotency_key=f"demo-{o4.pk}-{sku}",
            )
            inventory.consume(reservation=res, actor=tech)
        orders.transition(order=o4, to_status=OrderStatus.READY_FOR_PICKUP, actor=tech)
        inv4 = invoicing.issue_invoice(order=o4, actor=manager)
        invoicing.record_payment(
            invoice=inv4,
            amount=Decimal("50.00"),
            method="cash",
            actor=manager,
            idempotency_key=f"demo-{o4.pk}-deposit",
            note="Deposit at drop-off",
        )

        # 5. New order with an upcoming diagnosis appointment.
        o5 = orders.create_order(
            business=business,
            customer=sam,
            device=sam_console,
            problem_description="HDMI no signal after a power cut.",
            actor=manager,
        )
        scheduling.book(
            business=business,
            customer=sam,
            technician=tech2,
            starts_at=self._next_weekday(tz, 1, 10),
            duration_minutes=60,
            actor=manager,
            kind="diagnosis",
            order=o5,
        )

        # 6. Rejected estimate, then cancelled.
        o6 = orders.create_order(
            business=business,
            customer=chris,
            device=chris_laptop,
            problem_description="Several keys stopped working after a spill.",
            actor=manager,
            assigned_technician=tech,
        )
        self._repair(
            o6,
            tech,
            manager,
            [("part", parts["KB-MBA13"], "1"), ("labor", None, "2")],
            decide="reject",
        )
        orders.transition(
            order=o6,
            to_status=OrderStatus.CANCELLED,
            actor=manager,
            reason="Customer declined the estimate",
        )

        # 7. A request Chris sent through the customer portal.
        orders.create_order(
            business=business,
            customer=chris,
            device=chris_laptop,
            problem_description="Fan is very loud and the laptop gets hot when charging.",
            actor=users["customer"],
            priority="low",
            source=OrderSource.PORTAL,
        )

        scheduling.book(
            business=business,
            customer=amira,
            technician=tech,
            starts_at=self._next_weekday(tz, 2, 14),
            duration_minutes=30,
            actor=manager,
            kind="drop_off",
        )
        self.stdout.write("Created Fix-It Electronics.")
        return business

    def _repair(self, order, tech, manager, lines, decide: str) -> None:
        orders.transition(order=order, to_status=OrderStatus.DIAGNOSING, actor=tech)
        orders.record_diagnostics(
            order=order, findings="Fault confirmed during diagnosis.", actor=tech
        )
        est = estimates.create_version(order=order, actor=manager)
        estimates.replace_lines(
            estimate=est,
            lines=[
                {"part": item, "quantity": Decimal(qty)}
                if kind == "part"
                else {
                    "kind": "labor",
                    "description": "Labour",
                    "quantity": Decimal(qty),
                    "unit_price": order.business.default_labor_rate,
                }
                for kind, item, qty in lines
            ],
            notes="",
            actor=manager,
        )
        est, _ = estimates.send(estimate=est, actor=manager)
        estimates.decide(
            estimate=est,
            approve=decide == "approve",
            channel="staff",
            decided_by=manager,
            decided_by_name=order.customer.full_name,
            note="Confirmed by phone",
        )

    @transaction.atomic
    def _beta(self, users) -> Business:
        existing = Business.objects.filter(is_demo=True, name="Beta Gadget Clinic").first()
        if existing:
            self.stdout.write("Beta Gadget Clinic already exists; skipped.")
            return existing
        owner = users["owner_b"]
        business = create_business(
            owner=owner,
            name="Beta Gadget Clinic",
            timezone_name="America/New_York",
            currency="USD",
            tax_rate=Decimal("8.88"),
            is_demo=True,
            default_labor_rate=Decimal("60.00"),
        )
        self._activate(business, "starter")
        # The main demo owner also manages here, to show workspace switching.
        Membership.objects.create(business=business, user=users["owner"], role=Role.MANAGER)
        part = Part.objects.create(
            business=business,
            sku="BAT-PIX7",
            name="Pixel 7 battery",
            purchase_cost=Decimal("20"),
            selling_price=Decimal("59"),
            low_stock_threshold=Decimal("1"),
        )
        inventory.receive_stock(
            part=part, quantity=Decimal("3"), actor=owner, reason="Opening stock"
        )
        customer = Customer.objects.create(
            business=business,
            full_name="Dana White",
            phone="+1 212 555 0101",
            email="dana@example.com",
        )
        device = Device.objects.create(
            business=business, customer=customer, kind="phone", brand="Google", model="Pixel 7"
        )
        orders.create_order(
            business=business,
            customer=customer,
            device=device,
            problem_description="Battery swelling, back cover lifting.",
            actor=owner,
            priority="urgent",
        )
        self.stdout.write("Created Beta Gadget Clinic.")
        return business
