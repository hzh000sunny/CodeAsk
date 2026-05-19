import { expect, test, type Page } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_SESSION_LONG_UI_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

test.describe.configure({ timeout: 900_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_SESSION_LONG_UI_E2E=1 to run live long UI conversation E2E.",
);

test("long UI conversation preserves multiline user bubbles and runtime context", async ({
  page,
}) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  const enabledConfigCount = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    const configs = (await response.json()) as Array<{ enabled?: boolean }>;
    return configs.filter((config) => config.enabled).length;
  });
  test.skip(enabledConfigCount === 0, "No enabled real LLM config is available.");

  await page.goto("/#/sessions", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "新建会话" }).click();
  await expect(page.getByRole("textbox", { name: "会话输入" })).toBeEnabled();

  const firstQuestion = [
    "请用一句话回答：Python 中 list 和 tuple 的核心区别是什么？",
    "这是第二行，用来验证用户气泡是否保留换行。",
  ].join("\n");

  await sendThroughComposer(page, firstQuestion);
  const multilineText = await page
    .locator(".message-bubble[data-role='user'] .plain-message-content")
    .last()
    .evaluate((node) => node.textContent);
  expect(multilineText).toBe(firstQuestion);

  const firstUsage = await runtimeUsageLabel(page);
  expect(firstUsage).not.toBe("0k / 200k");

  const questions = [
    "继续只用一句话回答：你刚刚说 list 和 tuple 哪个不可变？",
    "再用一句话回答：写 Python 反转字符串最简单的表达式是什么？",
    "再用一句话回答：grep 和 awk 的核心区别是什么？",
    "最后结合前面上下文回答：我第一轮问题问的是哪两个 Python 类型？",
  ];

  let previousUsage = firstUsage;
  for (const question of questions) {
    await page.getByRole("textbox", { name: "会话输入" }).fill(question);
    await page.getByRole("button", { name: "发送" }).click();

    const streamingUsage = await runtimeUsageLabel(page);
    expect(streamingUsage).not.toBe("0k / 200k");

    await waitForTurnToFinish(page);
    const usage = await runtimeUsageLabel(page);
    expect(usage).not.toBe("0k / 200k");
    previousUsage = usage;
  }

  await expect(
    page
      .getByRole("region", { name: "会话消息" })
      .getByText(/list|tuple|列表|元组/i)
      .last(),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Agent 行动轨迹" })).toBeVisible();
  await expect(page.getByRole("region", { name: "会话运行状态" })).toContainText(
    previousUsage,
  );
});

async function sendThroughComposer(page: Page, content: string) {
  await page.getByRole("textbox", { name: "会话输入" }).fill(content);
  await page.getByRole("button", { name: "发送" }).click();
  await waitForTurnToFinish(page);
}

async function waitForTurnToFinish(page: Page) {
  await expect(page.getByRole("button", { name: "停止" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("button", { name: "发送" })).toBeVisible({
    timeout: 240_000,
  });
}

async function runtimeUsageLabel(page: Page) {
  return page
    .getByRole("region", { name: "会话运行状态" })
    .locator(".session-runtime-usage")
    .innerText();
}
