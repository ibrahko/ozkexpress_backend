FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev gdal-bin libgdal-dev \
    libgeos-dev libproj-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Development ────────────────────────────────────────────────────
FROM base as development

COPY requirements/ requirements/
RUN pip install -r requirements/local.txt

COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ── Production (Railway) ────────────────────────────────────────────
FROM base as production

COPY requirements/ requirements/
RUN pip install -r requirements/production.txt

COPY . .

# collectstatic et migrate sont dans start.sh (env vars pas disponibles au build)
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["bash", "start.sh"]
