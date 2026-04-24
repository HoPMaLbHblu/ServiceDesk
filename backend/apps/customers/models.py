from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from apps.core.models import PublicIdModel, TenantModel, TimeStampedModel


class Customer(PublicIdModel, TenantModel):
    full_name = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    # Visible to the customer in the portal (e.g. preferred pickup arrangements).
    customer_notes = models.TextField(blank=True)
    marketing_opt_in = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["business", "full_name"]),
            models.Index(fields=["business", "email"]),
            GinIndex(
                name="customer_search_trgm",
                fields=["full_name"],
                opclasses=["gin_trgm_ops"],
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def display_name(self) -> str:
        return f"{self.full_name} ({self.company})" if self.company else self.full_name


class CustomerNote(TenantModel):
    """Internal staff note about a customer. Never shown in the customer portal."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="internal_notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    body = models.TextField()

    class Meta:
        ordering = ["-created_at"]


class DeviceKind(models.TextChoices):
    PHONE = "phone", "Phone"
    TABLET = "tablet", "Tablet"
    LAPTOP = "laptop", "Laptop"
    DESKTOP = "desktop", "Desktop"
    CONSOLE = "console", "Game console"
    WEARABLE = "wearable", "Wearable"
    OTHER = "other", "Other"


class Device(PublicIdModel, TenantModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="devices")
    kind = models.CharField(max_length=20, choices=DeviceKind.choices, default=DeviceKind.PHONE)
    brand = models.CharField(max_length=80)
    model = models.CharField(max_length=120)
    serial_number = models.CharField(max_length=120, blank=True)
    imei = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True, help_text="Internal notes about the device.")

    class Meta:
        ordering = ["brand", "model"]
        indexes = [
            models.Index(fields=["business", "serial_number"]),
            models.Index(fields=["business", "customer"]),
        ]

    def __str__(self) -> str:
        serial = f" #{self.serial_number}" if self.serial_number else ""
        return f"{self.brand} {self.model}{serial}"


class CustomerPortalAccess(TimeStampedModel):
    """Explicit link that lets a user see one customer's records in the portal."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="portal_access")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portal_access"
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "user"],
                condition=Q(revoked_at__isnull=True),
                name="portal_access_one_active_link",
            )
        ]


class PortalInvitation(PublicIdModel, TimeStampedModel):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="portal_invitations"
    )
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
