import { defineConfig } from "@playwright/test";

// docker compose로 띄운 서비스를 상대로 돈다(docs/platform.md 8절).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 25_000 },
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.API_URL ?? "http://localhost:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
