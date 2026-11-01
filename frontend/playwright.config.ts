import { existsSync } from "node:fs";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests: the real frontend (a production build) through its /api proxy to the
 * real API, on a database of its own with a few Lisbon sights and a scripted LLM
 * (backend/tests/e2e). Needs the database from docker-compose; see README.md.
 */

const CI = Boolean(process.env.CI);
const API_PORT = 8100;
const WEB_PORT = 3100;
// As deployed: the API answers only requests the frontend's proxy forwards (src/proxy.ts).
const ORIGIN_SECRET = "e2e-origin-secret";
const backend = path.resolve(__dirname, "../backend");
const venvPython = path.join(
  backend,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const python = process.env.E2E_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  reporter: CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  expect: { timeout: 10_000 },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `"${python}" -m tests.e2e.server --port ${API_PORT}`,
      cwd: backend,
      env: { ORIGIN_SECRET },
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: !CI,
      timeout: 60_000,
    },
    {
      // A build of its own: the proxy's target is fixed when it builds.
      command: `npm run build && npm run start -- --port ${WEB_PORT}`,
      env: {
        BACKEND_URL: `http://127.0.0.1:${API_PORT}`,
        NEXT_DIST_DIR: ".next-e2e",
        ORIGIN_SECRET,
      },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !CI,
      timeout: 300_000,
    },
  ],
});
