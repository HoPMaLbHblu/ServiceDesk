# syntax=docker/dockerfile:1.7
# Django API, Celery worker and scheduler share this image.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
WORKDIR /app

FROM base AS deps-dev
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project

FROM base AS deps-prod
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project --no-dev

# Development: code is bind-mounted, runserver reloads on change.
FROM deps-dev AS dev
COPY backend/ ./
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Production: no dev tools, non-root user, static files collected at build time.
FROM deps-prod AS prod
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown app:app /app \
    && mkdir -p /data/media && chown app:app /data/media
COPY --chown=app:app backend/ ./
# Collect as the runtime user so the files and manifest are readable at run time.
USER app
RUN DJANGO_SETTINGS_MODULE=config.settings.prod DJANGO_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput
ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    PRIVATE_MEDIA_ROOT=/data/media
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live').status == 200 else 1)"
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
