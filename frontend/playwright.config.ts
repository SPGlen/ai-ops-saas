import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:8188",
    trace: "retain-on-failure",
  },
  reporter: [["list"], ["json", { outputFile: "../docs/e2e-report.json" }]],
  projects: [{ name: "desktop", use: { ...devices["Desktop Chrome"] } }],
});
