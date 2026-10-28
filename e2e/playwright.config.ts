import { defineConfig, devices } from "@playwright/test";

/** The end-to-end tests run against the Docker Compose stack behind nginx on port 80. */
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost";

export default defineConfig({
  testDir: "./tests",
  globalSetup: "./support/global-setup.ts",
  // One worker: every spec reads the same seeded database and none writes to it.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    locale: "es-ES",
    timezoneId: "Europe/Madrid",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
