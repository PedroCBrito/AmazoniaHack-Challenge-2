import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:5174",
    channel: process.env.PLAYWRIGHT_CHANNEL || "chromium",
    headless: true,
  },
  webServer: [
    {
      command: "python -m uvicorn tests.frontend_server:app --host 127.0.0.1 --port 8011",
      cwd: "..",
      url: "http://127.0.0.1:8011/live",
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5174 --strictPort",
      env: { API_PROXY_TARGET: "http://127.0.0.1:8011", VITE_API_BASE_URL: "/api" },
      url: "http://127.0.0.1:5174",
    },
  ],
});
