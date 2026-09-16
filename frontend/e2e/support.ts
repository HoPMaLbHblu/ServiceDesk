import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { expect, type Page } from "@playwright/test";

export const PASSWORD = "demo-pass-2024!";
export const ACCOUNTS = {
  owner: "owner@demo.servicedesk.test",
  manager: "manager@demo.servicedesk.test",
  technician: "tech@demo.servicedesk.test",
  customer: "customer@demo.servicedesk.test",
  ownerB: "owner.b@demo.servicedesk.test",
} as const;

const EMAIL_DIR =
  process.env.EMAIL_FILE_PATH ??
  resolve(import.meta.dirname, "../../backend/.e2e-emails");

export async function signIn(
  page: Page,
  email: string,
  workspace = "Fix-It Electronics",
) {
  if (new URL(page.url()).pathname !== "/login") await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => url.pathname !== "/login");
  // People with several workspaces pick one on first sign-in in a browser.
  if (new URL(page.url()).pathname === "/welcome") {
    await page.getByRole("button", { name: new RegExp(workspace) }).click();
    await page.waitForURL((url) => url.pathname !== "/welcome");
  }
}

/** Pick the first option of a <select> whose text contains `text`. */
export async function selectContaining(
  page: Page,
  label: string,
  text: string,
) {
  const select = page.getByRole("combobox", { name: label, exact: true });
  const value = await select
    .locator("option", { hasText: text })
    .first()
    .getAttribute("value");
  expect(value, `option containing "${text}" in ${label}`).toBeTruthy();
  await select.selectOption(value!);
}

/** Read the newest email whose subject contains `subject`, as Django's file backend wrote it. */
export function latestEmail(subject: string): string {
  const files = readdirSync(EMAIL_DIR)
    .map((name) => join(EMAIL_DIR, name))
    .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
  for (const file of files) {
    const messages = readFileSync(file, "utf8").split(/^-{79}$/m);
    for (const message of messages.reverse()) {
      // Undo quoted-printable soft line breaks so links come out whole.
      const text = message.replace(/=\r?\n/g, "").replace(/=3D/g, "=");
      if (text.includes(subject)) return text;
    }
  }
  throw new Error(`No email with "${subject}" in ${EMAIL_DIR}`);
}

export function linkIn(email: string, path: string): string {
  const match = email.match(new RegExp(`https?://[^\\s]+${path}[^\\s]*`));
  if (!match) throw new Error(`No ${path} link in email:\n${email}`);
  return match[0];
}
