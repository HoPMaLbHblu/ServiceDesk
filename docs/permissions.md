# Permissions

Every person in a workspace has one role there: **owner**, **manager** or **technician**. The same person can have a different role in another workspace. For example, the demo owner of Fix-It Electronics is a manager at Beta Gadget Clinic. Customers are not workspace members. They use the customer portal, which shows only the customer records an employee has linked to their account.

The server enforces every rule below. The frontend hides what a role cannot use, but it is not the security boundary.

## Matrix

O = owner, M = manager, T = technician, C = customer portal user.

For technicians, **own** means orders and appointments assigned to them, and the customers and devices on those orders. For customers, **own** means the customer records linked to their account.

| Capability | O | M | T | C |
| --- | --- | --- | --- | --- |
| **Workspace** | | | | |
| Dashboard reports and CSV exports | yes | no | no | no |
| Business settings: name, timezone, currency, tax, labor rate | yes | no | no | no |
| Business hours | edit | view | view | no |
| Invite members, change roles, remove members | yes | no | no | no |
| Choose a plan, open billing | yes | no | no | no |
| See the subscription state | yes | yes | yes | no |
| Audit log | yes | no | no | no |
| Email outbox, resend failed emails | yes | yes | no | no |
| **Customers and devices** | | | | |
| Create and edit customers and devices | yes | yes | no | no |
| View customers, devices and internal customer notes | all | all | own | no |
| Grant portal access to a customer | yes | yes | no | no |
| **Repair orders** | | | | |
| Create orders | yes | yes | no | send a request |
| Edit priority, technician, promised date, details | yes | yes | no | no |
| View orders | all | all | own | own, customer-visible fields only |
| Diagnostics, internal notes, customer updates | yes | yes | own | read customer updates |
| Move between statuses | every allowed move | every allowed move | own: start diagnosis, mark ready, back to repair | no |
| Cancel an order | yes | yes | no | no |
| Attachments | yes | yes | own | customer-visible only |
| **Appointments** | | | | |
| Book, reschedule, cancel | yes | yes | no | no |
| View appointments | all | all | own | own |
| Check free slots | yes | yes | yes | no |
| **Inventory** | | | | |
| Create and edit parts, receive stock, stock counts | yes | yes | no | no |
| View parts and stock movements | yes | yes | yes | no |
| Reserve, consume and release parts on an order | yes | yes | own | no |
| **Estimates** | | | | |
| Create, edit and send estimates | yes | yes | no | no |
| View estimates | all | all | own | own |
| Approve or decline | records a decision made by phone or in person | same as owner | no | own, from the portal or the emailed link |
| **Invoices** | | | | |
| Issue and void invoices, record payments and refunds | yes | yes | no | no |
| View invoices and download PDFs | yes | yes | no | own |

## Rules that are not about roles

- **Last owner.** A workspace always keeps at least one active owner. The last owner cannot be demoted or removed, and two owners demoting each other at the same moment cannot both succeed.
- **Other workspaces.** A record from another workspace behaves as if it does not exist (404), whatever the role. Removing someone from a workspace takes effect on their next request.
- **Read-only workspaces.** When the trial has ended, the subscription is cancelled, or payment is overdue beyond the grace period, every role can still read and export, but nobody can create or change records. Owners can still open billing to fix it.
- **Approval links** work without signing in. Each link is for one estimate version, can be used once and expires after 14 days.
- **Invitations** are for one email address, can be used once and expire after 7 days. Only owners with a verified email address can invite.
- **Plan limits.** Pending invitations count toward the plan's staff limit, so a workspace cannot invite past it.

Role checks are covered by `apps/businesses/tests/test_team.py` (`test_role_matrix`) and by each domain app's tests. Tenant isolation is covered by `apps/core/tests/test_tenant_isolation.py`.
