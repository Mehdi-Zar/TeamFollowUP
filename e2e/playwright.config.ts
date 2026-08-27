import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration.
 *
 * These tests drive the REAL application: the Docker image, serving the built
 * SPA and its API against a real PostgreSQL. They are deliberately not run
 * against `vite dev` with a stubbed API, because the bugs worth catching here
 * are the ones that only exist once the pieces are assembled - a route guard
 * that lets the wrong role through, a build that ships a stale chunk, a cookie
 * the browser refuses to send.
 *
 * Start the stack first (docs/18):
 *   docker compose up -d --build
 *   cd e2e && npx playwright test
 */
const BASE_URL = process.env.E2E_BASE_URL || "http://localhost:8000";

export default defineConfig({
  testDir: "./tests",
  // One worker: every test talks to the same database, and the suite creates and
  // deletes real records. Parallel workers would race on that shared state, and
  // a flaky E2E suite is one nobody trusts and everybody eventually disables.
  workers: 1,
  fullyParallel: false,
  // A failing assertion is a failing assertion. Retrying only in CI, and only
  // once, absorbs genuine infrastructure noise (a container still warming up)
  // without hiding a real intermittent bug behind three green retries.
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    // Both only on failure: traces are large, and a green run needs no evidence.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    // NOTE: this only sets the BROWSER locale. The app's language comes from the
    // server (Administration > general settings, `default_lang`, English out of
    // the box) and ignores the browser, so assertions below use English strings.
    // Pinned anyway so date and number formatting is stable across machines.
    locale: "en-GB",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
