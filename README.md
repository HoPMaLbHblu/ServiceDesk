# ServiceDesk

ServiceDesk is software for independent electronics repair shops. A shop takes in a device, diagnoses it, sends the customer an estimate to approve, does the repair with parts from its own stock, issues an invoice and records payments. Every business gets its own isolated workspace, and customers get a small portal where they can follow and approve their repairs.

It is a Django REST API (`backend/`) and a Vue 3 single-page app (`frontend/`), served from one origin behind nginx (`infrastructure/`).

## What it does

- **Customers and devices**, with internal notes and optional portal access for the customer.
- **Repair orders** with per-shop numbering (`RO-00042`), a state machine that explains why a move is refused, a timeline that cannot be edited afterwards, internal notes kept apart from customer updates, and photo and PDF attachments.
- **Appointments** on a week calendar. Business hours and the shop's timezone apply, and the database refuses to double-book a technician.
- **Inventory**: parts, stock receipts and counts, reservations for an order, and consumption when the part is fitted, all written to an append-only stock ledger.
- **Estimates** with versions. A customer approves one exact version, from an emailed single-use link or the portal, or staff record a decision taken by phone.
- **Invoices** built from the approved estimate and the parts used, with a PDF, partial payments, refunds and voiding.
- **Subscriptions** with plans and limits. A clearly labelled development billing mode needs no payment provider, and Stripe test mode is available.
- **Email** through a transactional outbox, with retries and a list of failures you can resend from.
- **Owner reports**: revenue, orders by status, technician workload and low stock, with CSV exports.
- **Audit log** of who changed what.
- **Accounts**: registration, email verification, password reset, invitations, several workspaces per person and a switcher between them.

Roles are owner, manager and technician, plus customer portal users. The full matrix is in [docs/permissions.md](docs/permissions.md).

## Run it in 3 steps

**1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)** and open it. Wait until it says *Engine running*.

**2. Copy and paste this** into a terminal (on Windows: PowerShell; on Mac: Terminal):

```sh
git clone https://github.com/HoPMaLbHblu/ServiceDesk.git
cd ServiceDesk
docker compose up --build -d
docker compose exec web sh -c "until python manage.py seed_demo; do sleep 3; done"
```

The first run downloads and builds everything, which takes a few minutes. The last line fills the app with demo data; if it prints a few errors first, that is fine, it retries until the database is ready.

**3. Open http://localhost:5173** and sign in:

- Email: `owner@demo.servicedesk.test`
- Password: `demo-pass-2024!`

That's it.

### Stop it / start it again

```sh
docker compose down      # stop
docker compose up -d     # start again (your data is kept)
```

### Something went wrong?

| Problem | Fix |
| --- | --- |
| `docker: command not found` or `cannot connect to the Docker daemon` | Docker Desktop isn't open. Open it, wait for *Engine running*, run the commands again. |
| `port is already allocated` / `ports are not available` | Another program uses that port. Close it, or restart the computer, then run `docker compose up -d`. |
| The page doesn't load | Wait 30 seconds and refresh; the app is still starting. |
| Start completely fresh | `docker compose down -v`, then repeat step 2 from `docker compose up --build -d`. |

### Other places to look

| URL | What |
| --- | --- |
| http://localhost:5173 | The app |
| http://localhost:8025 | Mailpit: every email the app "sends" lands here (estimate links, password resets) |
| http://localhost:5173/api/docs/ | API documentation |

## Demo accounts

Every password is `demo-pass-2024!`.

| Email | What you see |
| --- | --- |
| `owner@demo.servicedesk.test` | Shop owner: everything, including reports and billing |
| `manager@demo.servicedesk.test` | Manager |
| `tech@demo.servicedesk.test` | Technician: only the repair work |
| `customer@demo.servicedesk.test` | A customer: the portal where they follow and approve repairs |
| `owner.b@demo.servicedesk.test` | Owner of a second, separate shop |

The demo shop, Fix-It Electronics, already has repair orders in every state, stock, invoices and appointments. Beta Gadget Clinic is a second shop that shows workspaces are kept apart. Running `seed_demo` again is safe.

---

# Developer guide

## Running without Docker

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 and Redis 7 running locally.

```sh
# Backend: http://localhost:8000
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py seed_demo
uv run python manage.py runserver

# Worker and scheduler, in another terminal
cd backend && uv run celery -A config worker -B -l info

# Frontend: http://localhost:5173
cd frontend
npm ci
npm run dev
```

`config.settings.dev` is the default settings module. Without an SMTP server on port 1025, emails stay in the outbox and are retried, which you can see under Settings, Notifications.

## Tests and checks

| Command | What it checks |
| --- | --- |
| `cd backend && uv run pytest` | API, services and database constraints against a real PostgreSQL, including tenant isolation, role rules, concurrency races, money rounding, webhooks and the outbox |
| `cd backend && uv run ruff check . && uv run ruff format --check .` | Lint and formatting |
| `cd frontend && npm run typecheck` | `vue-tsc` in strict mode |
| `cd frontend && npm test` | Vitest unit and component tests |
| `cd frontend && npm run test:e2e` | Playwright against the real backend (see below) |
| `cd frontend && npm run build` | Production build |

The Playwright suite starts its own Django on port 8100 and Vite on port 5180. Django uses a separate database, `servicedesk_e2e`, which is dropped, migrated and seeded on every run. Tasks run inline and emails are written to `backend/.e2e-emails/`, so the tests can open the approval link a customer would receive. It needs local Postgres and Redis, the same as running without Docker.

## API types

The frontend's TypeScript types are generated from the OpenAPI schema:

```sh
cd backend && uv run python manage.py spectacular --file openapi.yaml
cd frontend && npm run api:types
```

## Repository layout

```
backend/          Django project (config/) and one app per domain (apps/)
frontend/         Vue 3 + TypeScript app, unit tests in src/, Playwright tests in e2e/
infrastructure/   Dockerfiles, nginx config, production compose file, backup scripts
docs/             Architecture, permissions, operations and known limitations
compose.yaml      Development stack
```

## Documentation

- [Architecture](docs/architecture.md): how tenancy, the workflows and the background jobs fit together.
- [Permissions](docs/permissions.md): what each role can do.
- [Operations](docs/operations.md): production configuration, TLS, billing, backups and restore.
- [Limitations](docs/limitations.md): what is deliberately out of scope or not finished.
- [Changelog](CHANGELOG.md): bugs fixed and features added since the first release.
- [Implementation plan](docs/implementation-plan.md): the original decisions.
