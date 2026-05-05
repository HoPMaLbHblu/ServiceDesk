from decimal import Decimal

from django.db import migrations

PLANS = [
    {"code": "starter", "name": "Starter", "price_monthly": Decimal("29.00"), "max_staff": 3, "max_orders_per_month": 150, "sort_order": 1},
    {"code": "professional", "name": "Professional", "price_monthly": Decimal("79.00"), "max_staff": 10, "max_orders_per_month": 1000, "sort_order": 2},
    {"code": "business", "name": "Business", "price_monthly": Decimal("149.00"), "max_staff": None, "max_orders_per_month": None, "sort_order": 3},
]


def create_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for plan in PLANS:
        Plan.objects.update_or_create(code=plan["code"], defaults=plan)


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_subscription_last_event_at")]

    operations = [migrations.RunPython(create_plans, migrations.RunPython.noop)]
