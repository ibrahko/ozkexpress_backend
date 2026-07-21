#!/bin/bash
set -e

echo "=== MotoExpress Backend - Démarrage ==="

echo ">>> Activation PostGIS..."
python manage.py setup_postgis

# Les migrations doivent être générées en développement (`makemigrations`)
# et commitées dans Git — jamais générées à la volée en production.
# Les générer au démarrage crée un risque de désynchronisation entre
# l'historique enregistré en base et les fichiers réellement déployés.
echo ">>> Migrations..."
python manage.py migrate --noinput

echo ">>> Fichiers statiques..."
# sans --clear : déjà collectés au build, on ne fait que compléter (démarrage plus rapide)
python manage.py collectstatic --noinput

echo ">>> Démarrage serveur ASGI..."
exec gunicorn config.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:${PORT:-8000} \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --timeout 120
