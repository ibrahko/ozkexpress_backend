import os
from pathlib import Path
from datetime import timedelta
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
APPS_DIR = BASE_DIR / "apps"

# Chemins GDAL/GEOS : uniquement sous Windows (dev local avec OSGeo4W).
# Sous Linux (Docker/Railway), les libs installées par apt sont trouvées automatiquement.
if os.name == "nt":
    _gdal = os.environ.get("GDAL_LIBRARY_PATH", r"C:\OSGeo4W\bin\gdal313.dll")
    _geos = os.environ.get("GEOS_LIBRARY_PATH", r"C:\OSGeo4W\bin\geos_c.dll")
    if os.path.exists(_gdal):
        GDAL_LIBRARY_PATH = _gdal
    if os.path.exists(_geos):
        GEOS_LIBRARY_PATH = _geos

env = environ.Env(DEBUG=(bool, False))
READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="change-me-in-production")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "django_filters",
    "channels",
    "channels_redis",
    "django_celery_beat",
    "django_celery_results",
    "cloudinary",
    "cloudinary_storage",
]

LOCAL_APPS = [
    "core",
    "apps.accounts",
    "apps.workforce",
    "apps.couriers",
    "apps.drivers",
    "apps.fleet",
    "apps.services",
    "apps.payments",
    "apps.tracking",
    "apps.disputes",
    "apps.notifications",
    "apps.analytics",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.request_id.RequestIDMiddleware",
    "core.middleware.logging.LoggingMiddleware",
    "core.middleware.timing.TimingMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

_DATABASE_URL = env("DATABASE_URL", default=None)

if _DATABASE_URL:
    # Railway injecte DATABASE_URL automatiquement
    import dj_database_url
    DATABASES = {
        "default": dj_database_url.parse(
            _DATABASE_URL,
            engine="django.contrib.gis.db.backends.postgis",
            conn_max_age=env.int("POSTGRES_CONN_MAX_AGE", default=60),
        )
    }
    DATABASES["default"]["OPTIONS"] = {"connect_timeout": 10}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.contrib.gis.db.backends.postgis",
            "NAME": env("POSTGRES_DB", default="motoexpress"),
            "USER": env("POSTGRES_USER", default="motoexpress"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="dev_pusko"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": env.int("POSTGRES_CONN_MAX_AGE", default=60),
            "OPTIONS": {"connect_timeout": 10},
        }
    }

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "motoexpress",
        "TIMEOUT": 300,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL], "capacity": 1500, "expiry": 10},
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "courier_location": "60/minute",
        "otp_verify": "5/minute",
        "otp_request": "3/minute",
        "payment_initiate": "10/minute",
        "service_create": "20/minute",
    },
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MotoExpress API",
    "DESCRIPTION": "API de livraison express par moto-taxi",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True

# Cloudinary
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET", default="")
if CLOUDINARY_CLOUD_NAME:
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Twilio
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="")
TWILIO_PHONE_NUMBER = env("TWILIO_PHONE_NUMBER", default="")

# Twilio WhatsApp (OTP) — canal moins cher que le SMS.
# TWILIO_WHATSAPP_NUMBER : numéro expéditeur au format "whatsapp:+14155238886"
# TWILIO_WHATSAPP_CONTENT_SID : SID du template "Authentication" approuvé par Meta
#   (variable {{1}} = code OTP ; bouton "Copy code" géré automatiquement par Meta)
TWILIO_WHATSAPP_NUMBER = env("TWILIO_WHATSAPP_NUMBER", default="")
TWILIO_WHATSAPP_CONTENT_SID = env("TWILIO_WHATSAPP_CONTENT_SID", default="")

# Canal d'envoi de l'OTP : "whatsapp" (recommandé, moins cher) ou "sms".
# Si le canal WhatsApp échoue (utilisateur sans WhatsApp, etc.), on retente en SMS.
OTP_CHANNEL = env("OTP_CHANNEL", default="whatsapp")

# Stripe
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")

# Orange Money
ORANGE_MONEY_API_URL = env("ORANGE_MONEY_API_URL", default="https://api.orange.com")
ORANGE_MONEY_CLIENT_ID = env("ORANGE_MONEY_CLIENT_ID", default="")
ORANGE_MONEY_CLIENT_SECRET = env("ORANGE_MONEY_CLIENT_SECRET", default="")

# Wave
WAVE_API_URL = env("WAVE_API_URL", default="https://api.wave.com/v1")
WAVE_API_KEY = env("WAVE_API_KEY", default="")

# Google Maps
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")

# App URL (pour les webhooks paiements)
APP_BASE_URL = env("APP_BASE_URL", default="http://localhost:8000")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
