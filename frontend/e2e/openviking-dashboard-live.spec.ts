import { expect, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

test.describe.configure({ timeout: 180_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENVIKING_E2E=1 to run the live OpenViking dashboard smoke.",
);

test("admin OpenViking dashboard survives reload and keeps host paths redacted", async ({
  page,
}) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  await page.goto("/#/settings?page=openviking", { waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "OpenViking", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("OpenViking RAG 状态")).toBeVisible();
  await expect(page.getByText("Ollama / 模型")).toBeVisible();
  await expect(page.getByText("bge-m3:latest")).toBeVisible();
  await expect(page.getByText("ready").last()).toBeVisible();
  await expect(page).toHaveURL(/#\/settings\?page=openviking$/);

  await page.reload({ waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "OpenViking", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/#\/settings\?page=openviking$/);

  const pageText = await page.locator("body").innerText();
  expect(pageText).not.toMatch(/\/home\/hzh|\/home\/codeask|\/tmp\//);
});
