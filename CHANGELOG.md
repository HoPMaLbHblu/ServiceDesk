# Changelog

## 2026-10-08

Found by testing the running app through its API with invalid and edge-case input. Each fix has a regression test.

### Bugs fixed

| # | Bug | What happened | Fix |
| --- | --- | --- | --- |
| 1 | Payments could be dated in the future | `received_at: 2099-01-01` was accepted, so the money appeared in a future period of the revenue report. | A payment can be at most 5 minutes in the future (to allow for clock drift). |
| 2 | Negative part prices crashed the server | Creating a part with a negative selling price or purchase cost returned a 500 error instead of a validation message. | The API now rejects negative prices with a message on the field. |
| 3 | Negative low-stock threshold crashed the server | Editing a part's low-stock threshold to a negative number returned a 500 error. | The API now rejects it with a message on the field. |
| 4 | Negative labour rate showed a database message | The error was `Constraint "business_labor_rate_gte_0" is violated`, not attached to any field. | Normal "must be 0 or more" message on the labour rate field. |
| 5 | Estimates could be valid for 0 days | Setting "estimate valid days" to 0 made every new estimate expire as soon as it was sent. | The minimum is now 1 day. |
| 6 | Very large estimates crashed the server | Quantity and price each passed validation, but their product was too big to store, giving a 500 error. | Line and estimate totals are checked against the largest storable amount and reported on the line. |
| 7 | Changing currency mixed amounts in reports | A shop could switch from GBP to EUR after issuing invoices. Reports add amounts together, so old pounds were shown as euros. | The currency is locked once the shop has estimates or invoices. |

### New

- **Overdue invoices.** The invoice list has an "Overdue only" filter and shows a red "Overdue" label next to the due date. An invoice is overdue when it is issued, not fully paid, and its due date has passed in the shop's timezone (the same rule the Reports page uses). The API has a matching `overdue` filter and an `is_overdue` field.

### Checked and working

Tenant isolation, role permissions, the order state machine, overpayment and refund limits, appointment double-booking, business hours and past-time checks, single-use approval links with change detection, file type checks on uploads, password rules, sign-in errors that don't reveal which emails exist, CSV exports protected against spreadsheet formulas, and repeat runs of `seed_demo`.
