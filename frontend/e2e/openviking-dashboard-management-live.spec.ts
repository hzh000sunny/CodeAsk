import { expect, type Page, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

type ApiResult<T> = {
  body: T;
  ok: boolean;
  status: number;
  text: string;
};

type SyncJob = {
  id: string;
  source_id: string;
  status: string;
};

type TuningResponse = {
  scopes: Record<
    string,
    Array<{
      key: string;
      previous_value: string | null;
      value: string;
    }>
  >;
};

type TuningPresetResponse = {
  preset: string;
  preset_values: Array<{
    key: string;
    recommended: string;
    scope: string;
  }>;
};

test.describe.configure({ timeout: 180_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENVIKING_E2E=1 to run live OpenViking dashboard management E2E.",
);

test("E2 embedding model switch is destructive and reserved for isolated data dirs", async () => {
  test.skip(
    true,
    "切 Embedding 模型会清理索引并触发全量重建；保留占位，需隔离数据目录执行。",
  );
});

test("E3 sync job shows real progress and can be retried from the UI", async ({
  page,
}) => {
  await loginAdmin(page);
  const sourceId = `mgmt-retry-${Date.now()}`;
  const enqueued = await api<{ id: string }>(page, "/api/admin/openviking/sync_jobs/enqueue", {
    body: {
      source_id: sourceId,
      source_type: "e2e_unknown",
    },
    method: "POST",
  });
  expect(enqueued.status).toBe(201);
  await expectOk(
    api(page, "/api/admin/openviking/sync_jobs/run_pending", { method: "POST" }),
  );
  await expect
    .poll(async () => findJobStatus(page, sourceId), { timeout: 30_000 })
    .toBe("failed");

  await openDashboard(page);
  const row = page.locator(".settings-openviking-job-row").filter({ hasText: sourceId });
  await expect(row).toBeVisible();
  await expect(row.getByRole("progressbar")).toHaveCount(0);
  await expect(row.getByText("状态 failed")).toBeVisible();

  await row.getByRole("button", { name: /重试 ovjob_/ }).click();
  await expect.poll(async () => findJobStatus(page, sourceId), { timeout: 30_000 }).toBe("pending");
  await expect(
    page.locator(".settings-openviking-row").filter({ hasText: "manual_retry" }).first(),
  ).toBeVisible();
});

test("E4 resync and rebuild index are destructive and reserved for isolated data dirs", async () => {
  test.skip(
    true,
    "rebuild_index 会清理向量库并重排全部任务；保留占位，需隔离数据目录执行。",
  );
});

test("E5 event stream filters by outcome and paginates", async ({ page }) => {
  await loginAdmin(page);
  for (let index = 0; index < 12; index += 1) {
    await expectOk(api(page, "/api/admin/openviking/sync_jobs/retry_failed", { method: "POST" }));
  }

  await openDashboard(page);
  await page.getByLabel("事件结果过滤").selectOption("info");
  await expect(
    page.locator(".settings-openviking-row").filter({ hasText: "manual_retry_failed" }).first(),
  ).toBeVisible();
  await page.getByLabel("事件类型过滤").selectOption("manual_retry_failed");

  const rows = page.locator(".settings-openviking-row").filter({ hasText: "manual_retry_failed" });
  await expect(rows.first()).toBeVisible();
  await expect(page.locator(".settings-openviking-event-count").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "加载更多" })).toBeVisible();
  await page.getByRole("button", { name: "加载更多" }).click();
  await expect(page.locator(".settings-openviking-event-count").first()).toBeVisible();
});

test("E6 and E8 tuning rejects invalid values, applies valid values, then rolls back", async ({
  page,
}) => {
  await loginAdmin(page);
  const original = await getTuningValue(page, "codeask", "sync_workers");
  const nextValue = original === "1" ? "2" : "1";
  await openDashboard(page);

  const tuningCard = page.getByLabel("OpenViking 调优参数");
  const input = tuningCard.getByRole("textbox", { name: "codeask.sync_workers" });
  await input.fill("10000");
  await tuningCard.getByRole("button", { name: "应用 codeask.sync_workers" }).click();
  await expect(tuningCard.getByText(/codeask\.sync_workers: value must be between/)).toBeVisible();
  await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(original);

  await input.fill(nextValue);
  await tuningCard.getByRole("button", { name: "应用 codeask.sync_workers" }).click();
  await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(nextValue);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "调优参数" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "codeask.sync_workers" })).toHaveValue(nextValue);

  const row = page
    .locator(".settings-openviking-tuning-row")
    .filter({ has: page.getByRole("textbox", { name: "codeask.sync_workers" }) });
  await row.getByRole("button", { name: /回滚/ }).click();
  await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(original);
});

test("E7 openviking-scope tuning restart is reserved for isolated data dirs", async () => {
  test.skip(
    true,
    "openviking scope 调参会重启 OpenViking；保留占位，需隔离数据目录执行。",
  );
});

test("E9 preset action applies recommended values without touching Ollama recommendations", async ({
  page,
}) => {
  await loginAdmin(page);
  const beforeCodeask = await getTuningValue(page, "codeask", "sync_workers");
  const beforeOpenViking = await getTuningValue(page, "openviking", "embedding.max_concurrent");
  const beforeOllama = await getTuningValue(page, "ollama_recommend", "num_parallel");
  const preset = await expectOk<TuningPresetResponse>(
    api(page, "/api/admin/openviking/tuning/preset"),
  );
  const codeaskTarget = presetValue(preset.body, "codeask", "sync_workers");
  const openVikingTarget = presetValue(
    preset.body,
    "openviking",
    "embedding.max_concurrent",
  );
  await openDashboard(page);

  try {
    const tuningCard = page.getByLabel("OpenViking 调优参数");
    await expect(tuningCard.getByText(`当前推荐预设：${preset.body.preset}`)).toBeVisible();
    page.once("dialog", async (dialog) => {
      expect(dialog.message()).toContain("套用预设");
      await dialog.accept();
    });
    await tuningCard.getByRole("button", { name: "套用预设" }).click();
    await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(
      codeaskTarget,
    );
    await expect.poll(async () => getTuningValue(page, "openviking", "embedding.max_concurrent")).toBe(
      openVikingTarget,
    );
    await expect.poll(async () => getTuningValue(page, "ollama_recommend", "num_parallel")).toBe(
      beforeOllama,
    );
  } finally {
    await restoreTuningValues(page, [
      { key: "sync_workers", scope: "codeask", value: beforeCodeask },
      { key: "embedding.max_concurrent", scope: "openviking", value: beforeOpenViking },
    ]);
  }
});

test("E10 Ollama systemd snippet is visible and copyable", async ({ context, page }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await loginAdmin(page);
  await openDashboard(page);

  const snippetBlock = page.locator(".settings-openviking-snippet");
  await expect(snippetBlock.locator("code")).toContainText("OLLAMA_NUM_PARALLEL");
  await expect(snippetBlock.locator("code")).toContainText("OLLAMA_NUM_THREAD");
  const snippet = await snippetBlock.locator("code").innerText();
  await snippetBlock.getByRole("button", { name: /复制/ }).click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(snippet);
});

test("E12 anonymous users cannot access management mutations", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expectOk(api(page, "/api/auth/logout", { method: "POST" }), [204]);
  const response = await api(page, "/api/admin/openviking/tuning", {
    body: {
      changes: [{ key: "sync_workers", scope: "codeask", value: "2" }],
    },
    method: "POST",
  });
  expect(response.status).toBe(403);
});

async function loginAdmin(page: Page) {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
}

async function openDashboard(page: Page) {
  await page.goto("/#/settings?page=openviking", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "OpenViking", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "健康状态" })).toBeVisible();
}

async function findJobStatus(page: Page, sourceId: string) {
  const result = await expectOk<{ items: SyncJob[] }>(
    api(page, "/api/admin/openviking/sync_jobs?limit=200"),
  );
  return result.body.items.find((item) => item.source_id === sourceId)?.status ?? "missing";
}

async function getTuningValue(page: Page, scope: string, key: string) {
  const result = await expectOk<TuningResponse>(api(page, "/api/admin/openviking/tuning"));
  const row = result.body.scopes[scope]?.find((item) => item.key === key);
  if (!row) {
    throw new Error(`missing tuning value ${scope}.${key}`);
  }
  return row.value;
}

function presetValue(preset: TuningPresetResponse, scope: string, key: string) {
  const row = preset.preset_values.find((item) => item.scope === scope && item.key === key);
  if (!row) {
    throw new Error(`missing preset value ${scope}.${key}`);
  }
  return row.recommended;
}

async function restoreTuningValues(
  page: Page,
  changes: Array<{ key: string; scope: string; value: string }>,
) {
  await expect
    .poll(
      async () => {
        const response = await api(page, "/api/admin/openviking/tuning", {
          body: { changes },
          method: "POST",
        });
        return response.status;
      },
      { timeout: 60_000 },
    )
    .toBe(200);
}

async function expectOk<T>(
  promise: Promise<ApiResult<T>>,
  statuses: number[] = [200, 201, 202],
): Promise<ApiResult<T>> {
  const result = await promise;
  expect(
    statuses.includes(result.status),
    `expected ${statuses.join("/")} but got ${result.status}: ${result.text}`,
  ).toBe(true);
  return result;
}

async function api<T>(
  page: Page,
  path: string,
  init: { body?: unknown; method?: string } = {},
): Promise<ApiResult<T>> {
  return page.evaluate(
    async ({ body: requestBodyPayload, method, path: requestPath }) => {
      const response = await fetch(requestPath, {
        body:
          requestBodyPayload === undefined
            ? undefined
            : JSON.stringify(requestBodyPayload),
        credentials: "same-origin",
        headers:
          requestBodyPayload === undefined
            ? undefined
            : { "Content-Type": "application/json" },
        method: method ?? "GET",
      });
      const text = await response.text();
      let body: unknown = null;
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          body = text;
        }
      }
      return {
        body,
        ok: response.ok,
        status: response.status,
        text,
      };
    },
    { body: init.body, method: init.method, path },
  ) as Promise<ApiResult<T>>;
}
