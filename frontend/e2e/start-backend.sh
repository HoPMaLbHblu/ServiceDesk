#!/bin/sh
# Starts Django for the Playwright suite on a freshly created database with demo data.
set -eu
cd "$(dirname "$0")/../../backend"
export DJANGO_SETTINGS_MODULE=config.settings.e2e
export EMAIL_FILE_PATH="${EMAIL_FILE_PATH:-$(pwd)/.e2e-emails}"

uv run python - <<'PY'
import django
import psycopg

django.setup()
from django.conf import settings

db = settings.DATABASES["default"]
if not db["NAME"].endswith("_e2e"):
    raise SystemExit(f"Refusing to reset {db['NAME']!r}: the e2e database name must end with _e2e")
with psycopg.connect(
    dbname="postgres", user=db["USER"], password=db["PASSWORD"], host=db["HOST"], port=db["PORT"], autocommit=True
) as conn:
    conn.execute(f'DROP DATABASE IF EXISTS "{db["NAME"]}" WITH (FORCE)')
    conn.execute(f'CREATE DATABASE "{db["NAME"]}"')
PY

rm -rf "$EMAIL_FILE_PATH"
uv run python manage.py migrate --noinput -v 0
uv run python manage.py seed_demo
exec uv run python manage.py runserver 127.0.0.1:8100 --noreload
