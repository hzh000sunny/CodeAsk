import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const SUBJECT_ID = "wiki_tail_live@dev";
const SUBJECT_KEY = "codeask.subject_id";

test("wiki sources, restore, and reindex work against the real backend", async ({
  page,
  request,
}) => {
  const featureId = await createFeature(request, "Live Wiki Tail Governance");
  await uploadLegacyMarkdownDocument(request, {
    featureId,
    filename: "Runbook.md",
    body: "# Runbook\n\n真实恢复内容。",
  });

  await setSubjectIdentity(page, SUBJECT_ID);
  await page.goto(`/#/wiki?feature=${featureId}`);

  await expect(page.locator(".wiki-page-header h1")).toHaveText("Runbook");
  await expect(page.getByText("真实恢复内容。")).toBeVisible();

  await page.locator(".wiki-floating-actions").getByRole("button", { name: "更多" }).click();
  await page.getByRole("menuitem", { name: "来源治理" }).click();
  const drawer = page.getByRole("dialog", { name: "来源治理" });
  await expect(drawer).toBeVisible();

  await drawer.getByRole("button", { name: "添加来源" }).click();
  await drawer.getByLabel("来源名称").fill("真实运行手册");
  await drawer.getByLabel("来源类型").selectOption("manual_upload");
  await drawer.getByLabel("URI / 路径").fill("file:///srv/live/runbook");
  await drawer.getByLabel("附加元数据").fill('{"root_path":"docs/live"}');
  await drawer.getByRole("button", { name: "保存来源" }).click();

  const sourceRow = drawer
    .locator("[data-testid^='wiki-source-row-']")
    .filter({ hasText: "真实运行手册" });
  await expect(sourceRow).toBeVisible();
  await expect(sourceRow).toContainText("手动录入");
  await expect(sourceRow).toContainText("docs/live");
  await expect(page.getByText("来源已创建")).toBeVisible();

  await sourceRow.getByRole("button", { name: "同步来源" }).click();
  await expect(sourceRow).toContainText("刚刚同步");
  await expect(page.getByText("来源同步成功")).toBeVisible();

  await drawer.getByRole("button", { name: "关闭来源治理" }).click();
  await expect(drawer).toHaveCount(0);

  await page.getByRole("button", { name: "打开节点 Runbook 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "删除" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();

  const restoreDialog = page.getByRole("dialog", { name: "Wiki 节点已删除，可恢复" });
  await expect(restoreDialog).toBeVisible();
  await restoreDialog.getByRole("button", { name: "恢复节点" }).click();
  await expect(page.getByText("Wiki 节点已恢复")).toBeVisible();
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Runbook");
  await expect(page.getByText("真实恢复内容。")).toBeVisible();

  await page.getByRole("button", { name: "打开节点 知识库 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "重新索引" }).click();
  await page.getByRole("button", { name: "确认重新索引" }).click();
  await expect(page.getByText("已重新索引 1 篇文档")).toBeVisible();
});

test("session attachment promotion writes a real wiki document and opens it", async ({
  page,
  request,
}) => {
  const featureId = await createFeature(request, "Live Session Promotion");
  const sessionId = await createSession(request, "真实会话附件晋级");
  await uploadSessionAttachment(request, {
    sessionId,
    filename: "startup-live.md",
    body: "# 启动排查记录\n\n真实会话附件晋级。",
  });

  await setSubjectIdentity(page, SUBJECT_ID);
  await page.goto("/#/sessions");

  await expect(
    page.getByRole("region", { name: "会话列表" }).getByText("真实会话附件晋级"),
  ).toBeVisible();
  const attachmentRegion = page.getByRole("region", { name: "会话数据" });
  await expect(attachmentRegion.getByText("startup-live.md")).toBeVisible();
  await attachmentRegion.getByRole("button", { name: "晋级为 Wiki startup-live.md" }).click();

  const dialog = page.getByRole("dialog", { name: "晋级为 Wiki" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("目标特性").selectOption(String(featureId));
  await expect(dialog.getByLabel("目标目录")).not.toHaveValue("");
  await dialog.getByLabel("Wiki 标题").fill("启动排查记录");
  await dialog.getByRole("button", { name: "确认晋级" }).click();

  const successDialog = page.getByRole("dialog", { name: "已写入 Wiki" });
  await expect(successDialog).toBeVisible();
  await expect(successDialog.getByText("启动排查记录")).toBeVisible();
  await successDialog.getByRole("button", { name: "打开 Wiki" }).click();

  await expect(page).toHaveURL(new RegExp(`#\\/wiki\\?feature=${featureId}&node=\\d+`));
  await expect(page.locator(".wiki-page-header h1")).toHaveText("启动排查记录");
  await expect(page.getByText("真实会话附件晋级。")).toBeVisible();
});

test("wiki tree ordering and edit-to-preview flow work against the real backend", async ({
  page,
  request,
}) => {
  const featureId = await createFeature(request, "Live Wiki Sort Edit");
  await uploadLegacyMarkdownDocument(request, {
    featureId,
    filename: "Alpha.md",
    body: "# Alpha\n\nAlpha 初始内容。",
  });
  await uploadLegacyMarkdownDocument(request, {
    featureId,
    filename: "Beta.md",
    body: "# Beta\n\nBeta 初始内容。",
  });

  await setSubjectIdentity(page, SUBJECT_ID);
  await page.goto(`/#/wiki?feature=${featureId}`);

  await expect(page.locator(".wiki-page-header h1")).toHaveText("Alpha");
  await expect
    .poll(async () => {
      const alphaY = await buttonVerticalPosition(page, "Alpha");
      const betaY = await buttonVerticalPosition(page, "Beta");
      return alphaY != null && betaY != null && alphaY < betaY;
    })
    .toBe(true);

  await page.getByRole("button", { name: "打开节点 Beta 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "上移" }).click();

  await expect
    .poll(async () => {
      const alphaY = await buttonVerticalPosition(page, "Alpha");
      const betaY = await buttonVerticalPosition(page, "Beta");
      return alphaY != null && betaY != null && betaY < alphaY;
    })
    .toBe(true);

  await page
    .getByRole("complementary", { name: "Wiki 目录树" })
    .getByRole("button", { name: "Beta", exact: true })
    .click();
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Beta");
  await expect(page.getByText("Beta 初始内容。")).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).click();
  await page.locator(".wiki-source-editor").fill("# Beta\n\nBeta 已保存到正式版本。");
  await page.getByRole("button", { name: "保存" }).click();

  await expect(page.getByRole("status")).toContainText("保存成功");
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Beta");
  await expect(page.getByText("Beta 已保存到正式版本。")).toBeVisible();
});

async function createFeature(request: APIRequestContext, name: string): Promise<number> {
  const response = await request.post("/api/features", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    data: {
      name: `${name} ${Date.now()}`,
      description: "Playwright live wiki tail verification",
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return Number(body.id);
}

async function createSession(request: APIRequestContext, title: string): Promise<string> {
  const response = await request.post("/api/sessions", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    data: { title },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return String(body.id);
}

async function uploadLegacyMarkdownDocument(
  request: APIRequestContext,
  payload: {
    featureId: number;
    filename: string;
    body: string;
  },
) {
  const response = await request.post("/api/documents", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    multipart: {
      feature_id: String(payload.featureId),
      file: {
        name: payload.filename,
        mimeType: "text/markdown",
        buffer: Buffer.from(payload.body, "utf-8"),
      },
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function uploadSessionAttachment(
  request: APIRequestContext,
  payload: {
    sessionId: string;
    filename: string;
    body: string;
  },
) {
  const response = await request.post(`/api/sessions/${payload.sessionId}/attachments`, {
    headers: { "X-Subject-Id": SUBJECT_ID },
    multipart: {
      kind: "doc",
      file: {
        name: payload.filename,
        mimeType: "text/markdown",
        buffer: Buffer.from(payload.body, "utf-8"),
      },
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function setSubjectIdentity(page: Page, subjectId: string) {
  await page.addInitScript(
    (payload: string[]) => {
      const [key, value] = payload;
      window.localStorage.setItem(key, value);
    },
    [SUBJECT_KEY, subjectId],
  );
}

async function buttonVerticalPosition(page: Page, name: string) {
  const box = await page
    .getByRole("complementary", { name: "Wiki 目录树" })
    .getByRole("button", { name, exact: true })
    .boundingBox();
  return box?.y ?? null;
}
