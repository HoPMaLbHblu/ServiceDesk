# ServiceDesk progress

This file is the persistent implementation checklist. It records what is done,
what remains, decisions and the commands needed to resume work.

## Checklist

- [x] Repository skeleton, implementation plan and role matrix
- [x] Backend foundation (settings, custom user, tenancy, audit)
- [x] Accounts: registration, verification, login, logout, password reset
- [x] Businesses: onboarding, memberships, invitations, workspace switching, last-owner protection
- [x] Customers and devices, portal access links
- [x] Repair orders: numbering, state machine, timeline, notes, attachments
- [x] Estimates: versions, approval links, approval on a specific version
- [x] Invoices and payments: numbering, snapshots, PDF, partial payments, refunds
- [x] Scheduling: hours, timezone, availability, exclusion constraint
- [x] Inventory: parts, stock, reservations, consumption, movements
- [x] Notifications: outbox, Celery tasks, retries, reminders, low stock
- [x] Subscriptions: plans, limits, dev billing mode, Stripe provider, webhooks
- [x] Reports and CSV exports
- [x] Frontend foundation (Vue, router, Pinia, Vue Query, Tailwind, API client)
- [x] Frontend screens for every workflow
- [x] Backend tests (isolation, roles, concurrency, money, webhooks, notifications)
- [x] Frontend unit tests
- [x] Playwright end-to-end tests against the real backend
- [x] Docker Compose, nginx, production configuration
- [x] Demo data command
- [x] Documentation: README, architecture, permissions, operations, limitations
- [x] Full-stack run and visual inspection (desktop and mobile)

## Last verification

| Check | Result |
| --- | --- |
| `uv run pytest` (backend) | 136 passed |
| `uv run ruff check .` and `ruff format --check .` | clean |
| `npm run typecheck` | clean |
| `npm test` (Vitest) | 44 passed in 10 files |
| `npm run test:e2e` (Playwright, real backend) | 6 passed (5 desktop, 1 mobile) |
| `npm run build` | succeeds |
| Production compose stack | built and started; `/api/health/ready` ok through nginx, SPA served with CSP, `seed_demo` and login work, worker and beat running |
| `backup.sh` against the production stack | dump and media archive written, checksums verify |
| `restore.sh` | not run end to end (see `docs/limitations.md`) |
| Screens on desktop and mobile | inspected for owner, technician and customer, no console errors |

## Open items

- Run `restore.sh` end to end on a disposable host.
- Bundle a Unicode font for invoice PDFs if non-Latin names are expected.
- See `docs/limitations.md` for everything deliberately out of scope.

## Decisions

See `docs/implementation-plan.md` and `docs/architecture.md`.

## Resume commands

```sh
# Full stack in Docker
cp .env.example .env && docker compose up --build
docker compose exec web python manage.py seed_demo

# Or locally (needs Postgres 16 and Redis 7)
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py seed_demo
uv run python manage.py runserver            # http://localhost:8000
uv run celery -A config worker -B -l info
cd frontend && npm ci && npm run dev         # http://localhost:5173

# Checks
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run typecheck && npm test && npm run test:e2e && npm run build

# Regenerate API types after backend API changes
cd backend && uv run python manage.py spectacular --file openapi.yaml
cd frontend && npm run api:types
```
