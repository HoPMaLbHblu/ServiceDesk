# ServiceDesk progress

This file is the persistent implementation checklist. It records what is done,
what remains, decisions and the commands needed to resume work.

## Checklist

- [x] Repository skeleton, implementation plan and role matrix
- [ ] Backend foundation (settings, custom user, tenancy, audit)
- [ ] Accounts: registration, verification, login, logout, password reset
- [ ] Businesses: onboarding, memberships, invitations, workspace switching, last-owner protection
- [ ] Customers and devices, portal access links
- [ ] Repair orders: numbering, state machine, timeline, notes, attachments
- [ ] Estimates: versions, approval links, approval on a specific version
- [ ] Invoices and payments: numbering, snapshots, PDF, partial payments, refunds
- [ ] Scheduling: hours, timezone, availability, exclusion constraint
- [ ] Inventory: parts, stock, reservations, consumption, movements
- [ ] Notifications: outbox, Celery tasks, retries, reminders, low stock
- [ ] Subscriptions: plans, limits, dev billing mode, Stripe provider, webhooks
- [ ] Reports and CSV exports
- [ ] Frontend foundation (Vue, router, Pinia, Vue Query, Tailwind, API client)
- [ ] Frontend screens for every workflow
- [ ] Backend tests (isolation, roles, concurrency, money, webhooks, notifications)
- [ ] Frontend unit tests
- [ ] Playwright end-to-end tests against the real backend
- [ ] Docker Compose, nginx, production configuration
- [ ] Demo data command
- [ ] Documentation: README, architecture, permissions, operations, limitations
- [ ] Full-stack run and visual inspection (desktop and mobile)

## Decisions

See `docs/implementation-plan.md`.

## Resume commands

_Filled in as the stack takes shape._
