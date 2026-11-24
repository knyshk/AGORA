// Browser tests: the backend is mocked per test (e2e/mocks.js), so no API keys or LLM calls are needed.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: { command: "npm run dev -- --port 5173 --strictPort", url: "http://localhost:5173",
               reuseExistingServer: !process.env.CI, timeout: 60_000 },
});
