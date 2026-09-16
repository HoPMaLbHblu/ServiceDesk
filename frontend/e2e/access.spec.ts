import { expect, test } from "@playwright/test";

import { ACCOUNTS, signIn } from "./support";

test("signed-out visitors are sent to sign in and come back afterwards", async ({
  page,
}) => {
  await page.goto("/customers");
  await expect(page).toHaveURL(/\/login\?next=(%2F|\/)customers$/);
  await signIn(page, ACCOUNTS.manager);
  await expect(page).toHaveURL(/\/customers$/);
});

test("switching workspace changes role, menu and data, and hides the other shop", async ({
  page,
}) => {
  await signIn(page, ACCOUNTS.owner);
  await expect(page.getByTestId("current-role")).toHaveText("owner");
  const nav = page.getByRole("navigation").first();
  await expect(nav.getByRole("link", { name: "Reports" })).toBeVisible();

  await page.goto("/customers");
  await expect(page.getByText("Chris Customer")).toBeVisible();
  await page.getByText("Chris Customer").click();
  await expect(page).toHaveURL(/\/customers\/[0-9a-f-]{36}$/);
  const fixItCustomerUrl = page.url();

  await page
    .getByTestId("workspace-switcher")
    .selectOption({ label: "Beta Gadget Clinic (manager)" });
  await expect(page.getByTestId("current-role")).toHaveText("manager");
  await expect(nav.getByRole("link", { name: "Reports" })).toHaveCount(0);

  await page.goto("/customers");
  await expect(page.getByText("Dana White")).toBeVisible();
  await expect(page.getByText("Chris Customer")).toHaveCount(0);

  // A record of the other workspace is not reachable by URL.
  await page.goto(fixItCustomerUrl);
  await expect(
    page.getByText(
      "This record does not exist or you do not have access to it.",
    ),
  ).toBeVisible();

  // The choice is remembered for the next sign-in in this browser.
  await page.getByTestId("logout").click();
  await signIn(page, ACCOUNTS.owner);
  await expect(page.getByTestId("current-role")).toHaveText("manager");
});

test("technicians do not see money pages", async ({ page }) => {
  await signIn(page, ACCOUNTS.technician);
  const nav = page.getByRole("navigation").first();
  await expect(nav.getByRole("link", { name: "Repair orders" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Invoices" })).toHaveCount(0);
  await page.goto("/invoices");
  await expect(
    page.getByRole("heading", { name: "You don't have access to this page" }),
  ).toBeVisible();
});

test("customers land in the portal and only see their own repairs @mobile", async ({
  page,
}) => {
  await signIn(page, ACCOUNTS.customer);
  await expect(page).toHaveURL(/\/portal/);
  await expect(page.getByRole("heading", { name: "My repairs" })).toBeVisible();
  await expect(page.getByText(/iPhone 13|MacBook Air/).first()).toBeVisible();
  await expect(page.getByText(/Galaxy S21|PlayStation 5/)).toHaveCount(0);
  // Staff pages are off limits.
  await page.goto("/orders");
  await expect(page).toHaveURL(/\/portal/);
});
