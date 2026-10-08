import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  projects: [{ name: "Microsoft Edge", use: { channel: "msedge" } }],
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  webServer: process.env.PLAYWRIGHT_EXTERNAL_SERVER
    ? undefined
    : {
        // This wrapper explicitly exits after Vite closes. That keeps Playwright's
        // supervised web server deterministic on Windows as well as Linux CI.
        command: "node ./scripts/preview.mjs",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: false,
        timeout: 15_000,
      },
});
