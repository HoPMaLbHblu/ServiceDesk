"""Settings shared by every environment. Secrets always come from the environment."""

from datetime import timedelta
from pathlib import Path

from config.env import env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

# Public base URL of the SPA, used in email links (verification, invitations, approvals).
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.businesses",
    "apps.audit",
    "apps.customers",
    "apps.orders",
    "apps.estimates",
    "apps.invoicing",
    "apps.scheduling",
    "apps.inventory",
    "apps.notifications",
    "apps.billing",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "servicedesk"),
        "USER": env("POSTGRES_USER", "servicedesk"),
        "PASSWORD": env("POSTGRES_PASSWORD", "servicedesk"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE", 60),
        "CONN_HEALTH_CHECKS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# All timestamps are stored in UTC. Each business has its own display timezone.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded files are private. They are never served directly by the web server;
# downloads go through authorized API views.
MEDIA_ROOT = Path(env("PRIVATE_MEDIA_ROOT", str(BASE_DIR / "media")))
MAX_UPLOAD_SIZE = env_int("MAX_UPLOAD_SIZE", 10 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE + 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_REDIS_URL", "redis://localhost:6379/1"),
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 12)
SESSION_SAVE_EVERY_REQUEST = True
CSRF_COOKIE_HTTPONLY = False  # The SPA reads the token and echoes it in X-CSRFToken.
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", "10/min"),
        "register": env("THROTTLE_REGISTER", "5/min"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", "5/min"),
        "sensitive": env("THROTTLE_SENSITIVE", "30/min"),
        "public_token": env("THROTTLE_PUBLIC_TOKEN", "30/min"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Proxies in front of Django that append to X-Forwarded-For (nginx, or the Vite dev proxy).
    # Rate limits key on the address the outermost trusted proxy saw; anything the client sent
    # before it is ignored. Set to 2 when a TLS proxy sits in front of nginx.
    "NUM_PROXIES": env_int("TRUSTED_PROXY_COUNT", 1),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ServiceDesk API",
    "DESCRIPTION": "REST API for the ServiceDesk repair-shop platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {
        "OrderStatusEnum": "apps.orders.models.OrderStatus",
        "PaymentStatusEnum": "apps.orders.models.PaymentStatus",
        "DeviceKindEnum": "apps.customers.models.DeviceKind",
        "EstimateStatusEnum": "apps.estimates.models.EstimateStatus",
        "EstimateLineKindEnum": "apps.estimates.models.LineKind",
        "InvoiceStatusEnum": "apps.invoicing.models.InvoiceStatus",
        "PaymentKindEnum": "apps.invoicing.models.PaymentKind",
        "AppointmentStatusEnum": "apps.scheduling.models.AppointmentStatus",
        "AppointmentKindEnum": "apps.scheduling.models.AppointmentKind",
        "ReservationStatusEnum": "apps.inventory.models.ReservationStatus",
        "MovementKindEnum": "apps.inventory.models.MovementKind",
        "NotificationStatusEnum": "apps.notifications.models.NotificationStatus",
        "NotificationKindEnum": "apps.notifications.models.NotificationKind",
        "OrderEventKindEnum": "apps.orders.models.EventKind",
    },
}

# Email
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 15)
# Used with the file-based backend (end-to-end tests read emails from here).
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH", str(BASE_DIR / "sent-emails"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "ServiceDesk <no-reply@servicedesk.local>")

# Tokens
EMAIL_VERIFICATION_MAX_AGE = timedelta(days=3)
INVITATION_MAX_AGE = timedelta(days=7)
ESTIMATE_APPROVAL_LINK_MAX_AGE = timedelta(days=14)

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 100
CELERY_TIMEZONE = "UTC"
# A single beat process owns every periodic job (see docker-compose "scheduler").
CELERY_BEAT_SCHEDULE = {
    "notifications-relay-outbox": {
        "task": "apps.notifications.tasks.relay_outbox",
        "schedule": timedelta(seconds=60),
    },
    "scheduling-appointment-reminders": {
        "task": "apps.scheduling.tasks.queue_appointment_reminders",
        "schedule": timedelta(minutes=15),
    },
}

NOTIFICATION_MAX_ATTEMPTS = env_int("NOTIFICATION_MAX_ATTEMPTS", 5)

# Billing: "dev" is a clearly labelled development mode; "stripe" uses Stripe test mode.
BILLING_PROVIDER = env("BILLING_PROVIDER", "dev")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")
BILLING_TRIAL_DAYS = env_int("BILLING_TRIAL_DAYS", 14)
BILLING_PAST_DUE_GRACE_DAYS = env_int("BILLING_PAST_DUE_GRACE_DAYS", 7)

# The seed_demo command refuses to run outside DEBUG unless this is set (e.g. a public demo server).
ALLOW_DEMO_DATA = env_bool("ALLOW_DEMO_DATA", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging.RequestIdFilter"},
    },
    "formatters": {
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}
