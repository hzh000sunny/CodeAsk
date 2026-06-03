import { expect, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

test.describe.configure({ timeout: 180_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENVIKING_E2E=1 to run the live OpenViking dashboard smoke.",
);

test("admin OpenViking dashboard survives reload and exposes diagnostic paths", async ({
  page,
}) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
  const statusResponse = await page.request.get("/api/admin/openviking/status");
  expect(statusResponse.ok()).toBe(true);
  const status = (await statusResponse.json()) as {
    version?: string | null;
    embedding?: { provider?: string | null; model?: string | null } | null;
    ollama?: { configured?: boolean | null } | null;
  };

  await page.goto("/#/settings?page=openviking", { waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "OpenViking", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "健康状态" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "同步任务" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "事件流" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "调优参数" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "运行指标" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Embedding 模型" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "VLM 模型" })).toBeVisible();
  const healthCard = page.locator(".openviking-card-health");
  await expect(healthCard.getByText("运行版本").first()).toBeVisible();
  await expect(healthCard.getByText("安装版本")).toHaveCount(0);
  if (status.version) {
    await expect(healthCard.getByText(status.version).first()).toBeVisible();
  }
  await expect(healthCard.getByText("模型后端").first()).toBeVisible();
  if (status.embedding?.provider && status.embedding.model) {
    await expect(
      healthCard.getByText(`${status.embedding.provider} / ${status.embedding.model}`).first(),
    ).toBeVisible();
  }
  await expect(healthCard.getByText("Ollama / 模型")).toHaveCount(0);
  await expect(healthCard.getByText("外部依赖")).toHaveCount(
    status.ollama?.configured ? 1 : 0,
  );
  await expect(page.getByText("未配置").first()).toBeVisible();
  await expect(page.getByLabel("事件结果过滤")).toBeVisible();
  await expect(page.getByLabel("事件类型过滤")).toBeVisible();
  await expect(page.getByRole("button", { name: "套用预设" })).toBeVisible();
  await expect(page.locator(".openviking-status-strip")).toHaveCount(0);
  await expect(page.getByText("Required model")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重建向量索引" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重排同步队列" })).toBeVisible();
  await expect(page.locator(".settings-openviking-card-header")).toHaveCount(8);
  await expect(page.locator(".openviking-dashboard .section-title-row")).toHaveCount(0);
  const diagnosticPaths = await page
    .locator(".settings-runtime-path-item code")
    .allTextContents();
  expect(
    diagnosticPaths.some((value) => value.startsWith("/") && value.endsWith("/openviking/ov.conf")),
    `expected absolute ov.conf path, got ${JSON.stringify(diagnosticPaths)}`,
  ).toBe(true);
  await expect(page).toHaveURL(/#\/settings\?page=openviking$/);

  await page.reload({ waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "OpenViking", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/#\/settings\?page=openviking$/);

  await expect
    .poll(async () => page.locator(".settings-runtime-path-item code").allTextContents())
    .toContainEqual(expect.stringMatching(/^\/.*\/openviking\/ov\.conf$/));
});
