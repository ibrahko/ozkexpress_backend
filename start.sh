#!/bin/bash
set -e

echo "=== MotoExpress Backend - Démarrage ==="

echo ">>> Activation PostGIS..."
python manage.py setup_postgis

echo ">>> Génération des migrations..."
python manage.py makemigrations --noinput

echo ">>> Migrations..."
python manage.py migrate --noinput

echo ">>> Fichiers statiques..."
python manage.py collectstatic --noinput --clear

echo ">>> Démarrage serveur ASGI..."
exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:${PORT:-8000} \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --timeout 120
