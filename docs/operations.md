# Operations

How to run ServiceDesk in production with the files in `infrastructure/`. The setup targets a single host with Docker Compose. It has Postgres, Redis, a migration job, gunicorn, a Celery worker, a single Celery beat scheduler and nginx.

## Production stack

```sh
cp .env.example .env     # then edit it, see below
docker compose -f infrastructure/compose.prod.yaml --env-file .env up -d --build
docker compose -f infrastructure/compose.prod.yaml --env-file .env exec web python manage.py createsuperuser
```

| Service | Image | Role |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | Database (volume `pgdata`) |
| `redis` | `redis:7-alpine`, append-only file on | Cache, rate limits, Celery broker (volume `redisdata`) |
| `migrate` | backend `prod` target | Runs `migrate` once, and `web` starts only after it succeeds |
| `web` | backend `prod` target | gunicorn, 3 workers, non-root user, health check on `/api/health/live` |
| `worker` | backend `prod` target | Celery worker: email delivery and other tasks |
| `scheduler` | backend `prod` target | Celery beat. Run exactly one. |
| `nginx` | frontend `prod` target | Serves the built app and proxies the API, listens on `HTTP_PORT` (default 80) |

Uploaded files live in the `media` volume, outside the web root. They are served only through authorized API endpoints with `Cache-Control: private, no-store`.

Upgrading means pulling the new code and running the same `up -d --build`. The `migrate` service applies migrations before the new `web` starts.

## Configuration

Settings come from environment variables in `.env`. The production settings module is `config.settings.prod`, and the image sets it.

| Variable | Required | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | yes | Long random string, for example `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | yes | Comma-separated host names, for example `app.example.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | yes | The public origin, for example `https://app.example.com` |
| `FRONTEND_URL` | yes | The public URL, used to build the links in emails |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | yes | Used by both Postgres and Django |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | yes | Your SMTP provider |
| `DEFAULT_FROM_EMAIL` | yes | A sender your SMTP provider accepts |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | default `true` | Leave them on behind HTTPS. Turn them off only to try the stack locally over plain HTTP. |
| `SECURE_HSTS_SECONDS` | default 30 days | Raise it once HTTPS is known to work everywhere |
| `BILLING_PROVIDER` | default `dev` | `dev` or `stripe`, see below |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | for Stripe | Test-mode keys only |
| `BILLING_TRIAL_DAYS` | default 14 | Trial length for new workspaces |
| `BILLING_PAST_DUE_GRACE_DAYS` | default 7 | How long a workspace stays writable after a failed payment |
| `MAX_UPLOAD_SIZE` | default 10 MB | Attachment size limit in bytes. nginx allows 12 MB bodies. |
| `NOTIFICATION_MAX_ATTEMPTS` | default 5 | Email delivery attempts before a notification is marked failed |
| `THROTTLE_LOGIN`, `THROTTLE_REGISTER`, `THROTTLE_PASSWORD_RESET`, `THROTTLE_SENSITIVE`, `THROTTLE_PUBLIC_TOKEN` | have defaults | Rate limits such as `10/min` |
| `TRUSTED_PROXY_COUNT` | default 1 | Proxies in front of Django that append `X-Forwarded-For`. 1 for the stack's nginx alone, 2 with a TLS proxy in front of it. Rate limits key on the address the outermost of these saw. |
| `LOG_LEVEL` | default `INFO` | |
| `ALLOW_DEMO_DATA` | default `false` | Set it only on a public demo server that should run `seed_demo` |
| `HTTP_PORT` | default 80 | Host port for nginx |

Never commit `.env`. It is in `.gitignore`.

## TLS

nginx in the stack speaks plain HTTP on port 80. Put a TLS-terminating proxy or load balancer in front of it, such as Caddy, Traefik, a cloud load balancer or another nginx. That proxy must:

- redirect HTTP to HTTPS,
- set `X-Forwarded-Proto: https`, which Django uses to know the request was secure (`SECURE_PROXY_SSL_HEADER`),
- pass the `Host` header through unchanged, because it must match `DJANGO_ALLOWED_HOSTS`,
- append the client address to `X-Forwarded-For`, and set `TRUSTED_PROXY_COUNT=2` so rate limits use that address. If the proxy does not append it, every visitor shares the proxy's address and its rate limit.

The health endpoints are exempt from the HTTPS redirect, so internal checks can use plain HTTP. Point load balancer checks at `/api/health/ready`, which also checks the database and Redis.

The nginx config sends a Content-Security-Policy that allows only same-origin scripts, styles, images and connections, plus `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and a Permissions-Policy that turns off camera, microphone and geolocation. Built assets under `/assets/` are cached for a year because their names contain a content hash. `index.html` is sent with `Cache-Control: no-cache`, so browsers check for a new release every time.

## Billing

**Development mode** (`BILLING_PROVIDER=dev`) is the default. Choosing a plan opens a page in the app, clearly labelled as simulated, where an owner can activate the plan or simulate a failed payment, a recovered payment or a cancellation. No money moves. Use it for development, demos and self-hosted installs that do not charge.

**Stripe test mode** (`BILLING_PROVIDER=stripe`):

1. In the Stripe dashboard, in test mode, create a product and a monthly price for each plan: Starter, Professional and Business.
2. Put each price id into the matching plan's `stripe_price_id` in the Django admin (`/admin/`, Billing, Plans).
3. Set `STRIPE_SECRET_KEY` to a test key (`sk_test_…` or `rk_test_…`). Live keys are refused at startup.
4. Add a webhook endpoint at `https://<your host>/api/v1/billing/webhooks/stripe/` for these events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_succeeded`, `invoice.payment_failed`. Put its signing secret into `STRIPE_WEBHOOK_SECRET`.

Webhooks are verified by signature and processed idempotently by event id. Events that arrive out of order do not roll a subscription back to an older state.

## Email

Email goes through the outbox described in [architecture.md](architecture.md#background-work). If SMTP is down, emails wait and are retried. Once the attempts run out they show as failed under Settings, Notifications, where owners and managers can resend them. In development, Mailpit at http://localhost:8025 catches everything.

## Backups

`infrastructure/scripts/backup.sh` writes a timestamped directory with:

- `database.dump`: `pg_dump` in custom format, compressed and consistent,
- `media.tar.gz`: uploaded attachments,
- `SHA256SUMS`: checksums of both.

```sh
infrastructure/scripts/backup.sh /srv/backups
```

Run it from the repository root, nightly from cron or a systemd timer, and copy the result off the host, for example to object storage with versioning. Keep several generations. Redis holds only caches, rate-limit counters and queued task messages, so it does not need a backup. Unsent emails are safe in Postgres and are picked up again by the outbox sweep.

## Restore

```sh
infrastructure/scripts/restore.sh /srv/backups/20260101T000000Z
```

The script verifies the checksums and asks you to type `restore`. Then it stops `web`, `worker` and `scheduler`, drops and recreates the database, restores the dump, replaces the media files and starts the services again. The append-only triggers are part of the schema, so they come back with the restore.

Practice a restore on a separate host now and then. A backup that has never been restored is not known to work.

Both scripts use the production compose file and `.env` by default. Set `COMPOSE` to use a different stack, for example `COMPOSE="docker compose -p staging -f infrastructure/compose.prod.yaml --env-file staging.env"`.

## Logs and monitoring

Every service logs to stdout. Django and Celery write JSON lines, each with a `request_id` that matches the `X-Request-ID` response header, so one request can be followed across log lines. Collect logs with your Docker logging driver of choice.

Things to watch:

- `/api/health/ready` returning anything other than 200,
- failed notifications, under Settings, Notifications, or `notifications_notification` rows with status `failed`,
- the worker and scheduler containers restarting,
- disk use of the `pgdata` and `media` volumes.

## Scaling notes

- `web` and `worker` can run more replicas. `scheduler` must stay at one, or periodic jobs run twice. Notification idempotency stops duplicate emails, but the work is still wasted.
- Media is on a local volume. To run `web` on more than one host, move attachments to shared storage first (see [limitations.md](limitations.md)).
- PostgreSQL is required: the appointment exclusion constraint, partial unique indexes and triggers do not exist in SQLite.
