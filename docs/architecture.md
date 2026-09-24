# Architecture

ServiceDesk is a modular monolith: one Django project with an app per domain, one PostgreSQL database, Celery for background work and a Vue single-page app. The browser talks to a single origin. In development Vite proxies `/api` to Django; in production nginx serves the built app and proxies `/api`, `/admin` and `/static`.

```
browser ──► nginx ──► /assets, index.html (built Vue app)
                 └──► /api, /admin, /static ──► gunicorn (Django + DRF)
                                                   │
                         PostgreSQL ◄──────────────┤
                         Redis (cache, throttles, Celery broker)
                                                   │
                         Celery worker ◄── tasks ──┘
                         Celery beat (one process, periodic jobs)
```

## Backend apps

| App | Responsibility |
| --- | --- |
| `core` | Tenancy, permissions, error format, money helpers, request ids and JSON logging, health checks, throttles, demo data |
| `accounts` | Custom user (email login), registration, verification, password reset, session API |
| `businesses` | Businesses, memberships and roles, invitations, workspace switching, per-business counters |
| `customers` | Customers, devices, internal notes, portal access links |
| `orders` | Repair orders, the state machine (`workflow.py`), timeline events, attachments |
| `estimates` | Estimate versions and lines, approval links, decisions |
| `invoicing` | Invoices, line snapshots, payments and refunds, PDF rendering |
| `scheduling` | Business hours, availability, appointments, reminders |
| `inventory` | Parts, stock levels, reservations, consumption, the stock ledger |
| `notifications` | The email outbox and its delivery tasks |
| `billing` | Plans, subscriptions, the billing provider interface (dev and Stripe), webhooks |
| `reports` | The owner dashboard and CSV exports |
| `audit` | The audit log |

Business rules live in each app's `services.py`. Views validate input, check permissions and call a service. Services run in a transaction, lock what they change and write the audit entry. This keeps rules in one place, so the API, the demo seed and the tests all go through the same code.

## Tenancy

All tenants share one schema. Every tenant-owned table has a `business` foreign key, and public ids are UUIDs, so ids cannot be guessed or enumerated.

- **The active workspace lives in the server session.** It is set only by `POST /api/v1/workspaces/switch/`, which checks membership. Ids sent in a request body are ignored.
- **Membership is checked again on every request** (`core.tenancy.resolve_tenant`). If someone is removed from a business, their next request is refused, even in a session that is already open. A session that points at a business the user does not belong to is cleared.
- **Querysets are always filtered by the active business** (`core.api.TenantViewMixin`). A record of another business is a plain 404, the same as a record that does not exist.
- **References in request bodies are resolved inside the active business** (`TenantRelatedField`, `StaffUserField`). An order cannot point at another shop's customer, device, technician or part.
- **Role checks** use `HasWorkspaceRole` with the owner, manager and staff role sets. Technicians are further limited to the orders and appointments assigned to them.
- **Billing gates writes, not reads.** `SubscriptionAllowsWrites` turns a workspace read-only when the trial has ended, the subscription was cancelled, or payment is past due beyond the grace period. Data stays readable and exportable, and owners can still reach billing.
- **The customer portal** has its own endpoints. A portal user sees only customers explicitly linked to their account through `CustomerPortalAccess`, and only fields marked as visible to the customer.

`apps/core/tests/test_tenant_isolation.py` builds a complete second business and checks that none of its records can be read, listed, changed or referenced from the first.

## Workflows and their guarantees

### Repair orders

`orders/workflow.py` defines the allowed transitions and the guards. A refused move returns a 409 with a specific code (`technician_required`, `estimate_not_approved`, `invoice_required` and others) and the list of moves that are allowed. Some moves are made only by the system: an order becomes `awaiting_approval` when an estimate is sent, and `scheduled` when an appointment is booked. `completed` and `cancelled` are final. Cancelling releases reserved parts and cancels booked appointments.

Edits use optimistic locking. The client sends the `version` it read, and a stale version returns 409 `stale_version` with the current version, so the UI can reload instead of overwriting someone else's change.

### Estimates

A draft estimate can be edited. Sending it freezes it as a version and emails the customer a link that is single-use and expires after 14 days. The token is stored only as a hash. A decision applies to one exact version: the request carries the version's content hash, so an approval cannot land on content the customer never saw. Revising creates a new version and makes older links stop working.

### Inventory

Stock rows are locked with `SELECT … FOR UPDATE`, and CHECK constraints keep on-hand and reserved quantities from going negative. Reservations and consumption take idempotency keys, so a retried request does not reserve twice. Every change writes a `StockMovement` row.

### Appointments

A PostgreSQL exclusion constraint (`btree_gist`) on technician and time range rejects overlapping active appointments, even when two requests arrive at the same moment. Availability takes the business hours in the business's timezone into account.

### Invoices and money

Money is `Decimal`, stored as `NUMERIC(12,2)` and rounded half up per line. Tax is computed once on the taxable subtotal. Invoices copy the lines they bill, so editing a part's price later does not change an issued invoice. Payments and refunds take idempotency keys. CHECK constraints keep amounts positive and tie every refund to a payment. The refund service locks the payment and refuses to refund more than is left on it. Invoice and order numbers come from a per-business counter row locked for the length of the transaction, so concurrent requests never share a number.

### Append-only records

Database triggers block `UPDATE` and `DELETE` on the order timeline (`orders_orderevent`), the stock ledger (`inventory_stockmovement`) and the audit log (`audit_auditlog`). Corrections are new rows.

## Background work

Celery uses Redis as its broker. Email follows the transactional outbox pattern:

1. A service writes a `Notification` row in the same transaction as the change that caused it.
2. After commit, a delivery task is queued.
3. The task sends the email and records the attempt. A failure is retried with backoff until `NOTIFICATION_MAX_ATTEMPTS` is reached, and then marked failed. Owners and managers can resend failed emails from Settings, Notifications.
4. Every minute the beat scheduler sweeps rows that are due and were never delivered, for example because the broker was down.

Each notification has an idempotency key, so the same event never emails twice. Bodies that contain a secret, such as a reset or approval link, are flagged and blanked after delivery.

The beat scheduler also queues appointment reminders every 15 minutes. Run exactly one beat process.

## Errors and API conventions

Every error uses one envelope:

```json
{ "error": { "code": "stale_version", "message": "…", "fields": {}, "details": {} } }
```

`fields` holds field validation errors, keyed by field name (`lines.0.quantity` for nested ones). The frontend shows `fields` next to the inputs and `message` for everything else. The schema is generated by drf-spectacular at `/api/schema/` and browsable at `/api/docs/`. The frontend's types are generated from it.

Authentication uses the Django session cookie (HttpOnly) with a CSRF header. Login, registration, password reset, sensitive actions and public approval links have their own rate limits, stored in Redis.

## Frontend

- Vue 3 with `<script setup>`, TypeScript in strict mode, Vite, Tailwind.
- **Pinia** holds the session: the user, their memberships, the active workspace and its role.
- **TanStack Vue Query** holds server data. Query keys start with `['ws', workspaceId]`, and the whole cache is cleared when the user or the workspace changes, so data from one shop never appears in another. Writes invalidate the active workspace's queries.
- **Routes** declare their layout, the roles allowed and whether they need a workspace, in `meta`. One guard enforces this. The server is still the authority, and the guard only avoids showing pages that would fail.
- **Forms** use `useApiForm`, which tracks unsaved changes, maps server field errors onto inputs and warns before leaving a page with unsaved edits.
- Estimate totals in the editor are computed with integer cents and the same rounding as the server, so the preview matches the saved estimate.

## Logging and health

Logs are JSON lines. Every request gets a request id, which is returned in the `X-Request-ID` header and included in every log line written during that request. `/api/health/live` reports whether the process is up. `/api/health/ready` also checks the database and the cache, and is what the container health checks and load balancers should use.
