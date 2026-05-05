import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  webServer: [
    {
      command:
        "bash -lc 'cd .. && rm -rf .tmp/playwright-e2e && mkdir -p .tmp/playwright-e2e && export CODEASK_DATA_DIR=$(pwd)/.tmp/playwright-e2e && export CODEASK_DATA_KEY=4lASQEQav_WrwbwO18ei221xkWwz-hHss5f58daoZoQ= && export CODEASK_HOST=0.0.0.0 && export CODEASK_PORT=8010 && export LITELLM_LOCAL_MODEL_COST_MAP=True && uv run codeask'",
      url: "http://127.0.0.1:8010/api/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command:
        "CODEASK_API_PROXY_TARGET=http://127.0.0.1:8010 corepack pnpm exec vite --host 0.0.0.0 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
