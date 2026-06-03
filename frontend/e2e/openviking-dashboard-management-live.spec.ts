import { expect, type Locator, type Page, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const DEFAULT_EMBEDDING_PROVIDER = "local";
const DEFAULT_EMBEDDING_MODEL = "bge-small-zh-v1.5-f16";
const DEFAULT_EMBEDDING_DIMENSION = 512;
const OLLAMA_EMBEDDING_BASE_URL =
  process.env.CODEASK_E2E_OLLAMA_EMBEDDING_BASE_URL ?? "http://127.0.0.1:11434";
const OLLAMA_EMBEDDING_MODEL = process.env.CODEASK_E2E_OLLAMA_EMBEDDING_MODEL ?? "bge-m3";
const OLLAMA_EMBEDDING_DIMENSION = Number(
  process.env.CODEASK_E2E_OLLAMA_EMBEDDING_DIMENSION ?? "1024",
);
const DEEPSEEK_VLM_PROVIDER = process.env.CODEASK_E2E_DEEPSEEK_VLM_PROVIDER ?? "litellm";
const DEEPSEEK_VLM_BASE_URL =
  process.env.CODEASK_E2E_DEEPSEEK_VLM_BASE_URL ?? "https://api.deepseek.com";
const DEEPSEEK_VLM_MODEL =
  process.env.CODEASK_E2E_DEEPSEEK_VLM_MODEL ?? "deepseek/deepseek-chat";
const DEEPSEEK_VLM_API_KEY =
  process.env.CODEASK_E2E_DEEPSEEK_VLM_API_KEY ?? "sk-codeask-e2e-deepseek-placeholder";

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

type EmbeddingResponse = {
  base_url: string | null;
  dimension: number | null;
  model: string;
  provider: string;
};

type LLMConfigResponse = {
  api_key_masked: string;
  base_url: string | null;
  enabled: boolean;
  id: string;
  model_name: string;
  name: string;
  protocol: string;
};

type SyncJobDetail = {
  attempts: number;
  id: string;
  source_id: string;
  status: string;
  task_id: string | null;
};

type VLMResponse = {
  base_url: string | null;
  enabled: boolean;
  model: string | null;
  provider: string | null;
};

// 这些 live 用例共用同一个后端 + 同一个 OpenViking 进程，且多数有状态（造失败任务 / 调参重启）。
// 并行执行会互相干扰（E5 的同步负载撞 E9 的调参重启），故串行跑。
test.describe.configure({ mode: "serial", timeout: 300_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENVIKING_E2E=1 to run live OpenViking dashboard management E2E.",
);

let createdSyncJobIds: string[] = [];

test.beforeEach(() => {
  createdSyncJobIds = [];
});

test.afterEach(async ({ page }) => {
  for (const jobId of createdSyncJobIds) {
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await api(page, "/api/admin/openviking/sync_jobs/run_pending", { method: "POST" });
      const response = await api(page, `/api/admin/openviking/sync_jobs/${jobId}`, {
        method: "DELETE",
      });
      if (response.status === 200 || response.status === 404) {
        break;
      }
      await page.waitForTimeout(500);
    }
  }
});

test("E2 embedding model switch covers default local and Ollama in the isolated data dir", async ({
  page,
}) => {
  await loginAdmin(page);
  const initialEmbedding = await expectOk<EmbeddingResponse>(
    api(page, "/api/admin/openviking/embedding"),
  );
  expect(initialEmbedding.body.provider).toBe(DEFAULT_EMBEDDING_PROVIDER);
  expect(initialEmbedding.body.model).toBe(DEFAULT_EMBEDDING_MODEL);
  expect(initialEmbedding.body.dimension).toBe(DEFAULT_EMBEDDING_DIMENSION);

  await openDashboard(page);
  const embeddingCard = page.getByLabel("OpenViking Embedding");
  await expect(embeddingCard.getByText(DEFAULT_EMBEDDING_MODEL).first()).toBeVisible();
  await embeddingCard.getByRole("button", { name: "测试" }).click();
  await expectSuccessfulDoctorTest(embeddingCard, 120_000);
  const afterDefaultTest = await expectOk<EmbeddingResponse>(
    api(page, "/api/admin/openviking/embedding"),
  );
  expect(afterDefaultTest.body.provider).toBe(DEFAULT_EMBEDDING_PROVIDER);
  expect(afterDefaultTest.body.model).toBe(DEFAULT_EMBEDDING_MODEL);

  await selectEmbeddingProvider(page, "ollama");
  await embeddingCard.getByLabel("Base URL").fill(OLLAMA_EMBEDDING_BASE_URL);
  await setLabeledControl(embeddingCard, "模型", OLLAMA_EMBEDDING_MODEL);
  await embeddingCard.getByLabel("维度").fill(String(OLLAMA_EMBEDDING_DIMENSION));
  await embeddingCard.getByRole("button", { name: "测试" }).click();
  await expectSuccessfulDoctorTest(embeddingCard, 120_000);

  await embeddingCard.getByRole("button", { name: "保存并切换" }).click();
  await confirmDashboardDialog(
    page,
    "确认切换 Embedding 配置",
    "确认保存",
    "清理 OpenViking 索引",
  );
  await expect
    .poll(async () => (await expectOk<EmbeddingResponse>(
      api(page, "/api/admin/openviking/embedding"),
    )).body.provider, { timeout: 90_000 })
    .toBe("ollama");
  const ollamaEmbedding = await expectOk<EmbeddingResponse>(
    api(page, "/api/admin/openviking/embedding"),
  );
  expect(ollamaEmbedding.body.base_url).toBe(OLLAMA_EMBEDDING_BASE_URL);
  expect(ollamaEmbedding.body.model).toBe(OLLAMA_EMBEDDING_MODEL);
  expect(ollamaEmbedding.body.dimension).toBe(OLLAMA_EMBEDDING_DIMENSION);
  await waitForOpenVikingHealthy(page);
});

test("E2b model config test is side-effect free and VLM save does not rebuild index", async ({
  page,
}) => {
  await loginAdmin(page);
  const deepSeekConfig = await ensureDeepSeekLlmConfig(page);
  const beforeEmbedding = await expectOk<EmbeddingResponse>(
    api(page, "/api/admin/openviking/embedding"),
  );
  const beforeVlm = await expectOk<VLMResponse>(api(page, "/api/admin/openviking/vlm"));
  const sourceId = `m13-vlm-${Date.now()}`;
  const enqueued = await api<{ id: string }>(page, "/api/admin/openviking/sync_jobs/enqueue", {
    body: {
      source_id: sourceId,
      source_type: "e2e_unknown",
    },
    method: "POST",
  });
  expect(enqueued.status).toBe(201);
  createdSyncJobIds.push(enqueued.body.id);
  await expect
    .poll(
      async () => {
        await expectOk(
          api(page, "/api/admin/openviking/sync_jobs/run_pending", { method: "POST" }),
        );
        return findJobStatus(page, sourceId);
      },
      { timeout: 90_000 },
    )
    .toBe("failed");
  const beforeJob = await getSyncJobBySourceId(page, sourceId);

  await openDashboard(page);
  const embeddingCard = page.getByLabel("OpenViking Embedding");
  await expect(embeddingCard.getByText(beforeEmbedding.body.model).first()).toBeVisible();
  await embeddingCard.getByRole("button", { name: "测试" }).click();
  await expectSuccessfulDoctorTest(embeddingCard, 60_000);
  const afterEmbeddingTest = await expectOk<EmbeddingResponse>(
    api(page, "/api/admin/openviking/embedding"),
  );
  expect(afterEmbeddingTest.body.provider).toBe(beforeEmbedding.body.provider);
  expect(afterEmbeddingTest.body.model).toBe(beforeEmbedding.body.model);

  const vlmCard = page.getByLabel("OpenViking VLM");
  await vlmCard.getByRole("switch", { name: "启用 VLM" }).click();
  await vlmCard.getByLabel("Provider").fill(DEEPSEEK_VLM_PROVIDER);
  await vlmCard.getByLabel("模型").fill(deepSeekConfig.model_name);
  await vlmCard.getByLabel("Base URL").fill(deepSeekConfig.base_url ?? "");
  await vlmCard.getByLabel("API Key").fill(DEEPSEEK_VLM_API_KEY);
  await vlmCard.getByRole("button", { name: "测试" }).click();
  await expectSuccessfulDoctorTest(vlmCard, 60_000);
  const afterVlmTest = await expectOk<VLMResponse>(api(page, "/api/admin/openviking/vlm"));
  expect(afterVlmTest.body.enabled).toBe(beforeVlm.body.enabled);
  expect(afterVlmTest.body.provider).toBe(beforeVlm.body.provider);
  expect(afterVlmTest.body.model).toBe(beforeVlm.body.model);

  await vlmCard.getByRole("button", { name: "保存", exact: true }).click();
  await confirmDashboardDialog(page, "确认更新 VLM 配置", "确认保存", "不会清理向量索引");
  await expect
    .poll(
      async () => (await expectOk<VLMResponse>(api(page, "/api/admin/openviking/vlm"))).body.enabled,
      { timeout: 60_000 },
    )
    .toBe(true);
  const afterVlmSave = await expectOk<VLMResponse>(api(page, "/api/admin/openviking/vlm"));
  expect(afterVlmSave.body.provider).toBe(DEEPSEEK_VLM_PROVIDER);
  expect(afterVlmSave.body.model).toBe(deepSeekConfig.model_name);
  expect(afterVlmSave.body.base_url).toBe(deepSeekConfig.base_url);
  const afterJob = await getSyncJobBySourceId(page, sourceId);
  expect(afterJob.status).toBe(beforeJob.status);
  expect(afterJob.attempts).toBe(beforeJob.attempts);
  expect(afterJob.task_id).toBe(beforeJob.task_id);

  await page.reload({ waitUntil: "domcontentloaded" });
  await openDashboard(page);
  const savedVlmCard = page.getByLabel("OpenViking VLM");
  await savedVlmCard.getByRole("button", { name: "禁用", exact: true }).click();
  await confirmDashboardDialog(page, "确认禁用 VLM", "确认禁用", "移除 ov.conf 中的 vlm 段");
  await expect
    .poll(
      async () => (await expectOk<VLMResponse>(api(page, "/api/admin/openviking/vlm"))).body.enabled,
      { timeout: 60_000 },
    )
    .toBe(false);
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
  createdSyncJobIds.push(enqueued.body.id);
  await expect
    .poll(
      async () => {
        await expectOk(
          api(page, "/api/admin/openviking/sync_jobs/run_pending", { method: "POST" }),
        );
        return findJobStatus(page, sourceId);
      },
      { timeout: 90_000 },
    )
    .toBe("failed");

  await openDashboard(page);
  const row = page.locator(".settings-openviking-job-row").filter({ hasText: sourceId });
  await expect(row).toBeVisible();
  await expect(row.getByRole("progressbar")).toHaveCount(0);
  await expect(row).toHaveAttribute("data-status", "failed");

  await row.getByRole("button", { name: /重试 ovjob_/ }).click();
  await confirmDashboardDialog(page, "确认重试同步任务", "确认重试", "确认重试同步任务");
  await expect.poll(async () => findJobStatus(page, sourceId), { timeout: 30_000 }).toBe("pending");
  await expect(
    page.locator('.settings-openviking-row[data-event-type="manual_retry"]').first(),
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
  // 生成足够多的 warning 事件用于分页：每个失败的 e2e_unknown 任务（attempts==1）发一条 sync_job_failed(warning)。
  // 注意：retry_failed 在无失败任务时按 §⑦ 不再发 count=0 噪声事件，故改用真实失败任务造数。
  const jobCount = 13;
  for (let index = 0; index < jobCount; index += 1) {
    const sourceId = `mgmt-evt-${Date.now()}-${index}`;
    const enqueued = await api<{ id: string }>(page, "/api/admin/openviking/sync_jobs/enqueue", {
      body: { source_id: sourceId, source_type: "e2e_unknown" },
      method: "POST",
    });
    expect(enqueued.status).toBe(201);
    createdSyncJobIds.push(enqueued.body.id);
  }
  await expect
    .poll(
      async () => {
        await expectOk(
          api(page, "/api/admin/openviking/sync_jobs/run_pending", { method: "POST" }),
        );
        const events = await expectOk<{ total: number }>(
          api(page, "/api/admin/openviking/events?view=all&event_type=sync_job_failed&limit=1"),
        );
        return events.body.total;
      },
      { timeout: 120_000 },
    )
    .toBeGreaterThanOrEqual(12);

  await openDashboard(page);
  await page.getByLabel("事件结果过滤").selectOption("warning");

  // 事件标题已人话化（§⑥），按机器枚举 data-event-type 选行，避免依赖展示文案。
  const rows = page.locator('.settings-openviking-row[data-event-type="sync_job_failed"]');
  const eventPagination = page.getByLabel("事件分页");
  await expect(rows.first()).toBeVisible();
  await expect(page.getByLabel("事件每页条数")).toHaveValue("5");
  await expect(eventPagination.getByText(/共 \d+ 条 · 第 1 \/ \d+ 页/)).toBeVisible();
  await page.getByLabel("事件页码").fill("2");
  await page.getByRole("button", { name: "跳转事件页" }).click();
  await expect(eventPagination.getByText(/共 \d+ 条 · 第 2 \/ \d+ 页/)).toBeVisible();
  await expect(page.getByText("正在查看历史事件页，实时刷新暂停")).toBeVisible();
  await page.getByLabel("事件每页条数").selectOption("10");
  await expect(page.getByLabel("事件每页条数")).toHaveValue("10");
  await expect(eventPagination.getByText(/共 \d+ 条 · 第 1 \/ \d+ 页/)).toBeVisible();
  await page.getByRole("button", { name: "下一页事件" }).click();
  await expect(eventPagination.getByText(/共 \d+ 条 · 第 2 \/ \d+ 页/)).toBeVisible();
  await page.getByRole("button", { name: "上一页事件" }).click();
  await expect(eventPagination.getByText(/共 \d+ 条 · 第 1 \/ \d+ 页/)).toBeVisible();
});

test("E6 and E8 tuning rejects invalid values, applies valid values, then restores original value", async ({
  page,
}) => {
  await loginAdmin(page);
  const original = await getTuningValue(page, "codeask", "sync_workers");
  const nextValue = original === "1" ? "2" : "1";
  await openDashboard(page);

  const tuningCard = page.getByLabel("OpenViking 调优参数");
  const codeaskScope = tuningCard.locator(".tuning-scope-summary").filter({ hasText: "CodeAsk 同步" });
  const input = codeaskScope.getByRole("textbox", { name: "自定义值 codeask.sync_workers" });
  if (!(await input.isVisible())) {
    await codeaskScope.locator("summary").first().click();
  }
  await input.fill("10000");
  await codeaskScope.getByRole("button", { name: "应用 codeask.sync_workers" }).click();
  await confirmDashboardDialog(page, "确认应用调优参数", "确认应用", "codeask.sync_workers");
  await expect(tuningCard.getByText(/codeask\.sync_workers: value must be between/)).toBeVisible();
  await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(original);

  await input.fill(nextValue);
  await codeaskScope.getByRole("button", { name: "应用 codeask.sync_workers" }).click();
  await confirmDashboardDialog(page, "确认应用调优参数", "确认应用", "codeask.sync_workers");
  await expect.poll(async () => getTuningValue(page, "codeask", "sync_workers")).toBe(nextValue);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "调优参数" })).toBeVisible();
  await restoreTuningValues(page, [{ key: "sync_workers", scope: "codeask", value: original }]);
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
    await tuningCard.getByRole("button", { name: "套用预设" }).click();
    await confirmDashboardDialog(page, "确认套用预设", "确认套用", "套用");
    await expect
      .poll(async () => getTuningValue(page, "codeask", "sync_workers"), { timeout: 60_000 })
      .toBe(codeaskTarget);
    await expect
      .poll(
        async () => getTuningValue(page, "openviking", "embedding.max_concurrent"),
        { timeout: 60_000 },
      )
      .toBe(openVikingTarget);
    await expect
      .poll(async () => getTuningValue(page, "ollama_recommend", "num_parallel"), { timeout: 60_000 })
      .toBe(beforeOllama);
    await waitForOpenVikingHealthy(page);
  } finally {
    await restoreTuningValues(page, [
      { key: "sync_workers", scope: "codeask", value: beforeCodeask },
      { key: "embedding.max_concurrent", scope: "openviking", value: beforeOpenViking },
    ]);
    await waitForOpenVikingHealthy(page);
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
  await snippetBlock.getByRole("button", { name: "验证 Ollama 设置" }).click();
  await expect(snippetBlock.getByText(/验证通过|验证未通过/)).toBeVisible();
  await expect(
    page.locator('.settings-openviking-row[data-event-type="ollama_settings_verified"]').first(),
  ).toBeVisible();
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

async function selectEmbeddingProvider(page: Page, provider: string) {
  const embeddingCard = page.getByLabel("OpenViking Embedding");
  await embeddingCard.getByLabel("Provider").selectOption(provider);
}

async function setLabeledControl(
  scope: ReturnType<Page["getByLabel"]>,
  label: string,
  value: string,
) {
  const control = scope.getByLabel(label);
  const tagName = await control.evaluate((element) => element.tagName.toLowerCase());
  if (tagName === "select") {
    await control.selectOption(value);
    return;
  }
  await control.fill(value);
}

async function expectSuccessfulDoctorTest(scope: Locator, timeout: number) {
  const result = scope.locator('.settings-openviking-doctor-line[data-ok="true"]').filter({
    hasText: "测试结果",
  });
  await expect(result).toBeVisible({ timeout });
}

async function ensureDeepSeekLlmConfig(page: Page): Promise<LLMConfigResponse> {
  const configs = await expectOk<LLMConfigResponse[]>(api(page, "/api/admin/llm-configs"));
  const existing = configs.body.find(
    (config) =>
      config.protocol === "openai" &&
      config.base_url === DEEPSEEK_VLM_BASE_URL &&
      config.model_name === DEEPSEEK_VLM_MODEL,
  );
  if (existing) {
    return existing;
  }

  const created = await expectOk<LLMConfigResponse>(
    api(page, "/api/admin/llm-configs", {
      body: {
        name: `DeepSeek VLM E2E ${Date.now()}`,
        protocol: "openai",
        base_url: DEEPSEEK_VLM_BASE_URL,
        api_key: DEEPSEEK_VLM_API_KEY,
        model_name: DEEPSEEK_VLM_MODEL,
        max_tokens: 512,
        enabled: false,
      },
      method: "POST",
    }),
  );
  expect(created.body.api_key_masked).not.toEqual("");
  return created.body;
}

async function findJobStatus(page: Page, sourceId: string) {
  const result = await expectOk<{ items: SyncJob[] }>(
    api(page, "/api/admin/openviking/sync_jobs?source_type=e2e_unknown&limit=100"),
  );
  return result.body.items.find((item) => item.source_id === sourceId)?.status ?? "missing";
}

async function getSyncJobBySourceId(page: Page, sourceId: string) {
  const result = await expectOk<{ items: SyncJobDetail[] }>(
    api(page, "/api/admin/openviking/sync_jobs?source_type=e2e_unknown&limit=100"),
  );
  const job = result.body.items.find((item) => item.source_id === sourceId);
  if (!job) {
    throw new Error(`missing sync job ${sourceId}`);
  }
  return job;
}

async function waitForOpenVikingHealthy(page: Page) {
  await expect
    .poll(
      async () => {
        const response = await api<{
          health?: { healthy?: boolean };
          running?: boolean;
        }>(page, "/api/admin/openviking/status");
        if (response.status !== 200) {
          return false;
        }
        return response.body.running === true && response.body.health?.healthy === true;
      },
      { timeout: 120_000 },
    )
    .toBe(true);
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

async function confirmDashboardDialog(
  page: Page,
  title: string,
  confirmLabel: string,
  expectedText: string,
) {
  const dialog = page.getByRole("dialog", { name: title });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(expectedText);
  await dialog.getByRole("button", { name: confirmLabel }).click();
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
