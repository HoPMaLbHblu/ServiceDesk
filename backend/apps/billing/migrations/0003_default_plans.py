from django.db import migrations

from apps.billing.plans import ensure_default_plans


def create_plans(apps, schema_editor):
    ensure_default_plans(apps.get_model("billing", "Plan"))


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_subscription_last_event_at")]

    operations = [migrations.RunPython(create_plans, migrations.RunPython.noop)]
