"""
Settings pour le déploiement Railway (test/staging).
Railway gère SSL au niveau du load balancer, donc on désactive SECURE_SSL_REDIRECT.
"""
import os
from urllib.parse import urlparse, parse_qs
from .base import *

DEBUG = False

ALLOWED_HOSTS = ["*"]

# CORS : autoriser l'app mobile (Expo)
CORS_ALLOW_ALL_ORIGINS = True

# SSL géré par Railway, pas par Django
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Base de données via DATABASE_URL (Supabase / Railway Postgres)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    DATABASES["default"] = {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "sslmode": "require",  # Supabase exige SSL
        },
    }

# Redis — override explicite pour Railway (django-environ ne résout pas les références Railway)
_REDIS_URL = os.environ.get("REDIS_URL", "")
if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "motoexpress",
            "TIMEOUT": 300,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [_REDIS_URL], "capacity": 1500, "expiry": 10},
        }
    }
    CELERY_BROKER_URL = _REDIS_URL
    CELERY_RESULT_BACKEND = _REDIS_URL

# Sécurité
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)
