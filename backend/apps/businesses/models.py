import zoneinfo
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.core.models import PublicIdModel, TimeStampedModel

CURRENCY_CHOICES = [
    ("USD", "US dollar"),
    ("EUR", "Euro"),
    ("GBP", "British pound"),
    ("CAD", "Canadian dollar"),
    ("AUD", "Australian dollar"),
    ("UAH", "Ukrainian hryvnia"),
    ("PLN", "Polish zloty"),
]


def validate_timezone(value: str) -> None:
    if value not in zoneinfo.available_timezones():
        raise ValidationError(f"{value} is not a known timezone.")


class Business(PublicIdModel, TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone])
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default="USD")
    # Percentage applied to taxable estimate and invoice lines, e.g. 8.25 for 8.25%.
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    default_labor_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    estimate_valid_days = models.PositiveSmallIntegerField(default=14)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False, help_text="Created by the demo-data command.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name_plural = "businesses"
        constraints = [
            models.CheckConstraint(
                condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100), name="business_tax_rate_range"
            ),
            models.CheckConstraint(
                condition=Q(default_labor_rate__gte=0), name="business_labor_rate_gte_0"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def tzinfo(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.timezone)


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    TECHNICIAN = "technician", "Technician"


STAFF_MANAGERS = frozenset({Role.OWNER, Role.MANAGER})


class Membership(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "user"], name="membership_unique_business_user"
            ),
        ]
        indexes = [models.Index(fields=["user", "is_active"])]

    def __str__(self) -> str:
        return f"{self.user} @ {self.business} ({self.role})"


class Invitation(PublicIdModel, TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices)
    # Only a SHA-256 hash of the token is stored; the raw token travels in the email link.
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "business",
                Lower("email"),
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="invitation_one_pending_per_email",
            ),
        ]

    @property
    def status(self) -> str:
        from django.utils import timezone

        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "pending"


class BusinessCounter(models.Model):
    """Gap-tolerant, per-business sequence used for order and invoice numbers."""

    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=40)
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="counter_unique_name")
        ]
