# =============================================================================
# EduVision AI — Backend Dockerfile
# =============================================================================
# Multi-stage build: builder, development, build, production
# =============================================================================

# ---- Builder Stage ----
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev curl ffmpeg libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Development Stage ----
FROM python:3.13-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=development \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev curl ffmpeg libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN pip install --no-cache-dir watchdog

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD curl --fail http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ---- Build Stage (for production) ----
FROM development AS build

COPY . /app

RUN python -m compileall -q /app

# ---- Production Stage ----
FROM python:3.13-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    HOME=/app \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev curl ffmpeg libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    mkdir -p /app/uploads && \
    chown -R app:app /app

COPY --chown=app:app --from=build /app /app

# Ensure storage directories are owner-writable. Windows/OneDrive host
# directories can carry a ReadOnly attribute that Docker bakes into the
# image as mode 555, which breaks local-storage writes at runtime.
RUN mkdir -p /app/storage-data/eduvision-content/sources \
             /app/storage-data/eduvision-content/thumbnails \
             /app/storage-data/eduvision-content/exports \
             /app/storage-data/eduvision-public \
    && chmod -R u+rwX /app/storage-data \
    && chown -R app:app /app/storage-data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl --fail http://localhost:8000/api/v1/health || exit 1

CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120"]
