import { expect, test } from "@playwright/test";

import {
  ACCOUNTS,
  latestEmail,
  linkIn,
  selectContaining,
  signIn,
} from "./support";

test("a repair goes from intake to a part-paid invoice, with the customer approving by email", async ({
  page,
  browser,
}) => {
  await signIn(page, ACCOUNTS.manager);

  // Intake.
  await page.getByRole("link", { name: "Repair orders" }).first().click();
  await page.getByRole("link", { name: "New repair order" }).click();
  await page.getByLabel("Find customer").fill("Chris");
  await page
    .getByRole("listbox", { name: "Matching customers" })
    .getByRole("button", { name: /Chris Customer/ })
    .click();
  await selectContaining(page, "Device", "iPhone 13");
  await page
    .getByLabel("Problem reported by the customer")
    .fill("Dropped it, screen is cracked and touch is dead in the top half.");
  await selectContaining(page, "Technician", "Tara Technician");
  await page.getByRole("button", { name: "Create order" }).click();

  await expect(page).toHaveURL(/\/orders\/[0-9a-f-]{36}$/);
  const heading = await page.getByRole("heading", { level: 1 }).textContent();
  const reference = heading!.match(/RO-\d+/)![0];
  await expect(page.getByTestId("order-status")).toHaveText("New");

  // Diagnosis and estimate.
  await page.getByRole("button", { name: "Start diagnosis" }).click();
  await expect(page.getByTestId("order-status")).toHaveText("Diagnosing");
  await page.getByRole("button", { name: "Create estimate" }).click();
  const editor = page.getByTestId("estimate-editor");
  await editor.getByRole("button", { name: "+ Labor" }).click();
  await editor.getByLabel("Unit price for line 1").fill("45.00");
  await editor.getByRole("button", { name: "+ Part" }).click();
  await selectContaining(page, "Part for line 2", "iPhone 13 screen");
  // 45.00 labor + 149.00 screen, plus 20% VAT.
  await expect(editor.getByTestId("estimate-total")).toHaveText("£232.80");
  await editor.getByRole("button", { name: "Send to customer" }).click();
  await expect(page.getByTestId("order-status")).toHaveText(
    "Awaiting approval",
  );

  // The customer approves from the emailed link, without signing in.
  const email = latestEmail(`Estimate for ${reference}`);
  const approvalUrl = linkIn(email, "/approve/");
  const customer = await browser.newContext();
  const approval = await customer.newPage();
  await approval.goto(approvalUrl);
  await expect(approval.getByText(reference)).toBeVisible();
  await approval.getByTestId("approve-estimate").click();
  await expect(
    approval.getByText("Thank you. The shop has been notified"),
  ).toBeVisible();
  // The link is single use.
  await approval.reload();
  await expect(
    approval.getByText("A decision was already recorded with this link."),
  ).toBeVisible();
  await customer.close();

  // Back at the shop: start the repair, invoice it, take a deposit.
  await page.reload();
  await expect(page.getByTestId("estimates-panel")).toContainText(
    "Approved by Chris Customer",
  );
  const startRepair = page.getByRole("button", { name: "Start repair" });
  if (await startRepair.isVisible()) await startRepair.click();
  await expect(page.getByTestId("order-status")).toHaveText("In progress");
  await page.getByRole("button", { name: "Issue invoice" }).click();

  await expect(page).toHaveURL(/\/invoices\/[0-9a-f-]{36}$/);
  await expect(page.getByTestId("balance-due")).toHaveText("£232.80");
  await page.getByRole("button", { name: "Record payment" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Amount").fill("100.00");
  await dialog.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByTestId("balance-due")).toHaveText("£132.80");
  await expect(page.getByTestId("invoice-status")).toHaveText("Partially paid");
});
