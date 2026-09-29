# Known limitations

What ServiceDesk does not do yet, or does in a simpler way than a large deployment would need. Each item says what to change if it matters for you.

## Product scope

- **Email only.** There are no SMS or WhatsApp notifications. Appointment reminders and estimate links go by email.
- **English only.** The interface and emails are not translated. Dates, times and money are formatted for each business's timezone and currency.
- **Invoice PDFs use the built-in Helvetica font.** Latin text renders correctly, but names or addresses in other scripts, such as Cyrillic or Arabic, do not. The fix is to bundle a Unicode TTF font (for example DejaVu Sans) and register it in `apps/invoicing/pdf.py`.
- **One tax rate per business**, applied to taxable lines. There are no per-line rates, tax-inclusive prices or tax exemption certificates.
- **No payment collection from customers.** Payments are recorded by staff (cash, card terminal, transfer). Customers cannot pay an invoice online.
- **Portal access is granted by staff.** A customer cannot sign up and claim their records themselves. This is deliberate, to avoid leaking repair history to someone who only knows an email address.
- **Reports are computed on request.** This is fine for the volume of one shop. Large businesses would want pre-aggregated tables.
- **No purchase orders or suppliers.** Stock is received manually with a reason. There is no reorder workflow beyond the low-stock list.
- **No warranty or return tracking** after an order is completed.

## Accounts and security

- **No multi-factor authentication** and no single sign-on.
- **Sessions only.** There is no API token authentication for third-party integrations.
- **Rate limits are per client address, per signed-in user, and per email for login and password reset, stored in Redis.** The client address comes from `X-Forwarded-For` as appended by the trusted proxies, so `TRUSTED_PROXY_COUNT` must match your proxy chain (see [operations.md](operations.md#tls)).
- **Uploads are checked by their content signature** (JPEG, PNG, GIF, PDF) and by size, but not scanned for malware.

## Billing

- **Stripe runs in test mode only.** Live keys are refused on purpose. Going live needs a review of tax, invoicing and dunning rules for the business selling ServiceDesk.
- **The Stripe integration has not been run against a real Stripe account in this repository's checks.** Webhook handling is tested with constructed events signed with the webhook secret (`apps/billing/tests/test_billing.py`). The calls that create Stripe checkout and billing-portal sessions have no automated tests.
- **Plan limits** cover staff seats and repair orders per month. Storage is not metered.

## Infrastructure

- **Single host.** The compose files run everything on one machine. Attachments are on a local Docker volume, so running `web` on several hosts needs shared storage first. Django's storage API makes moving to S3-compatible storage a settings change plus a data copy.
- **TLS is expected in front of the stack.** nginx in the stack serves plain HTTP (see [operations.md](operations.md#tls)).
- **No built-in metrics endpoint.** There are health checks and structured logs, but no Prometheus metrics or tracing.
- **The restore procedure is not fully exercised by the automated checks.** `backup.sh` was run against the production stack and its checksums and archive verified. The drop-and-restore steps of `restore.sh` were reviewed but not run end to end in the sandbox used to build this. Practise a restore on a separate host before relying on it.

## Testing

- **End-to-end tests cover the main flows**: intake to a part-paid invoice with customer approval by email, sign-in redirects, workspace switching, role menus, cross-workspace URLs and the customer portal. Less common screens, such as stock counts, refunds, voiding and the billing simulator, are covered by backend and unit tests, not by browser tests.
- **The E2E suite runs in Chromium only**, with one desktop and one mobile viewport.
