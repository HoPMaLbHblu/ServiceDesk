from decimal import Decimal

DEFAULT_PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "price_monthly": Decimal("29.00"),
        "max_staff": 3,
        "max_orders_per_month": 150,
        "sort_order": 1,
    },
    {
        "code": "professional",
        "name": "Professional",
        "price_monthly": Decimal("79.00"),
        "max_staff": 10,
        "max_orders_per_month": 1000,
        "sort_order": 2,
    },
    {
        "code": "business",
        "name": "Business",
        "price_monthly": Decimal("149.00"),
        "max_staff": None,
        "max_orders_per_month": None,
        "sort_order": 3,
    },
]


def ensure_default_plans(plan_model) -> None:
    """Create the default plans if missing. Existing plans (and their Stripe price ids) are kept."""
    for plan in DEFAULT_PLANS:
        plan_model.objects.get_or_create(code=plan["code"], defaults=plan)
