# ServiceDesk implementation plan

ServiceDesk is a multi-tenant SaaS for independent repair shops, starting with
electronics repair. It is a modular monolith: a Django REST API (`backend/`)
and a Vue 3 single-page application (`frontend/`), served same-origin behind a
reverse proxy (`infrastructure/`).

## Decisions

| Topic | Decision |
| --- | --- |
| Django | 5.2 LTS (supported until April 2028), DRF, drf-spectacular |
| Database | PostgreSQL 16, shared schema, explicit `business_id` foreign keys |
| Auth | Django session cookie (HttpOnly) + CSRF header, same origin in dev via Vite proxy and in prod via nginx |
| Active workspace | Stored in the server session, set only through `POST /api/v1/workspaces/switch/`, which validates membership. Membership is re-validated on every request. The browser never supplies a business id that is trusted. |
| Customer portal | `CustomerPortalAccess` links a user to a specific customer record. Portal endpoints only see records of linked customers. |
| Estimate approval links | Signed, expiring, single-estimate-version tokens (hashed at rest) |
| Concurrency: appointments | PostgreSQL exclusion constraint (`btree_gist`) on technician + time range for active appointments |
| Concurrency: inventory | Row locks (`SELECT ... FOR UPDATE`) on stock rows, CHECK constraints for non-negative stock, idempotency keys on reservation and consumption |
| Numbering | Per-business counters locked with `SELECT ... FOR UPDATE`, unique `(business, number)` constraints |
| Money | `Decimal` everywhere, `NUMERIC(12,2)`, ROUND_HALF_UP at line level |
| Background jobs | Celery + Redis; notifications use a transactional outbox swept by a single beat scheduler |
| Billing | Provider abstraction: `dev` (labelled development mode, default) and `stripe` (test mode when keys exist) |
| Email in dev | Mailpit |
| PDF | ReportLab (pure Python, no system dependencies) |

## Role matrix

`O` = owner, `M` = manager, `T` = technician, `C` = customer portal user.
"Own" for technicians means orders or appointments assigned to them.
"Own" for customers means records of customers explicitly linked to their
user account.

| Capability | O | M | T | C |
| --- | --- | --- | --- | --- |
| View dashboard and reports, export CSV | yes | no | no | no |
| Manage business settings, hours, tax, currency | yes | no | no | no |
| Invite members, change roles, remove members | yes | no | no | no |
| Manage subscription and billing | yes | no | no | no |
| View audit log | yes | no | no | no |
| Create / edit customers and devices | yes | yes | no | no |
| View customer and device details | yes | yes | own orders only | own |
| Internal customer notes | yes | yes | read on own orders | no |
| Grant customer portal access | yes | yes | no | no |
| Create repair orders | yes | yes | no | request only |
| View repair orders | all | all | own | own (customer-visible fields only) |
| Assign technician, set priority and due date | yes | yes | no | no |
| Record diagnostics | yes | yes | own | no |
| Order transitions | all permitted | all permitted | own: start diagnosis, mark ready | no |
| Cancel order | yes | yes | no | no |
| Internal notes on orders | yes | yes | own | no |
| Customer-visible updates | yes | yes | own | read |
| Attachments (upload / download) | yes | yes | own | customer-visible only |
| Appointments: create, reschedule, cancel | yes | yes | read own | read own |
| Technician availability | yes | yes | read own | no |
| Parts catalog and stock adjustments | yes | yes | read | no |
| Reserve / consume / release parts | yes | yes | own orders | no |
| Prepare and send estimates | yes | yes | no | no |
| Approve or reject estimate | on behalf of customer, recorded as such | on behalf of customer, recorded as such | no | own |
| Issue invoices, record payments and refunds | yes | yes | no | no |
| View invoices | yes | yes | no | own |
| Retry failed notifications | yes | yes | no | no |

The last active owner of a business cannot be removed, demoted or deactivated.

## Order workflow

```
new ──► scheduled ──► diagnosing ──► awaiting_approval ──► in_progress ──► ready_for_pickup ──► completed
 │          │             ▲   │              │   ▲               │
 │          │             │   └──────────────┘   └───────────────┘ (new estimate version needed)
 │          └─► diagnosing (walk-in skip)    rejected ─► diagnosing
 └──────────────► diagnosing

cancel: new, scheduled, diagnosing, awaiting_approval, in_progress, ready_for_pickup ──► cancelled
```

- `awaiting_approval` requires a sent estimate version.
- `in_progress` requires the latest estimate version to be approved.
- `completed` requires an issued invoice. Payment status is tracked separately
  (`unpaid`, `partially_paid`, `paid`, `refunded`) and shown alongside.
- `completed` and `cancelled` are terminal. No API edits the order afterwards.

## Build order

1. Repository skeleton, plan, progress checklist.
2. Backend foundation: settings, custom user, tenancy core, audit log, errors.
3. Vertical slice: registration → business → customer → order → estimate
   approval → completion → invoice → payment (API + Vue).
4. Scheduling, inventory, notifications, subscriptions, reports.
5. Tests: tenant isolation, roles, concurrency on PostgreSQL, money, webhooks.
6. Docker Compose, reverse proxy, docs, demo data.
7. Run the full stack, inspect screens, fix issues.
