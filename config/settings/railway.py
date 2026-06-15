"""
Settings pour le déploiement Railway (test/staging).
Railway gère SSL au niveau du load balancer, donc on désactive SECURE_SSL_REDIRECT.
"""
import os
from .base import *

DEBUG = False

# Railway injecte automatiquement RAILWAY_PUBLIC_DOMAIN
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
ALLOWED_HOSTS = ["*"] if not RAILWAY_PUBLIC_DOMAIN else [RAILWAY_PUBLIC_DOMAIN, f"www.{RAILWAY_PUBLIC_DOMAIN}"]

# CORS : autoriser l'app mobile (Expo)
CORS_ALLOW_ALL_ORIGINS = True

# SSL géré par Railway, pas par Django
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Railway injecte DATABASE_URL automatiquement
import dj_database_url
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=120,
        engine="django.contrib.gis.db.backends.postgis",
    )

# Sécurité
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)
