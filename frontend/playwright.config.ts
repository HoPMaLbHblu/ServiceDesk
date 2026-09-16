import { defineConfig, devices } from "@playwright/test";

// The suite runs against the real Django backend on its own database
// (servicedesk_e2e), recreated and seeded with demo data on every run.
const FRONTEND = "http://localhost:5180";
const BACKEND = "http://127.0.0.1:8100";

export default defineConfig({
  testDir: "./e2e",
  // Tests share one seeded database and change it, so they run one at a time.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: FRONTEND,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] }, grep: /@mobile/ },
  ],
  webServer: [
    {
      command: "sh e2e/start-backend.sh",
      url: `${BACKEND}/api/health/live`,
      reuseExistingServer: false,
      timeout: 180_000,
      stdout: "ignore",
      stderr: process.env.E2E_SERVER_LOGS ? "pipe" : "ignore",
    },
    {
      command: "npx vite --port 5180 --strictPort",
      url: `${FRONTEND}/login`,
      env: { VITE_DEV_BACKEND_URL: BACKEND },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
