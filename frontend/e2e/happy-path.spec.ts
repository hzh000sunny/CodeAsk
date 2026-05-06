import { expect, test, type Page, type Route } from "@playwright/test";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_e2e",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

const repo = {
  id: "repo_e2e",
  name: "codeask",
  source: "local_dir",
  url: null,
  local_path: "/repo/codeask",
  bare_path: "/tmp/repos/repo_e2e/bare",
  status: "ready",
  error_message: null,
  last_synced_at: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

const globalPolicy = {
  id: "skill_e2e",
  name: "证据引用规范",
  scope: "global",
  feature_id: null,
  stage: "answer_finalization",
  enabled: true,
  priority: 20,
  prompt_template: "回答必须引用证据 ID。",
};

test("source-list workbench happy path", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");

  const primaryNav = page.getByRole("navigation", { name: "主导航" });
  await expect(primaryNav).toBeVisible();
  await expect(
    primaryNav.getByRole("button", { name: "会话", exact: true }),
  ).toHaveAttribute("aria-current", "page");

  await page
    .getByRole("textbox", { name: "会话输入" })
    .fill("支付服务启动失败");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(
    page
      .getByRole("region", { name: "会话消息" })
      .getByText("需要检查启动配置。")
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "调查进度" }).getByText("知识检索"),
  ).toBeVisible();
  const sessionList = page.getByRole("region", { name: "会话列表" });
  await sessionList
    .getByRole("button", { name: "打开会话 线上启动失败 的更多操作" })
    .click();
  await page.getByRole("menuitem", { name: "删除" }).click();
  await expect(page.getByRole("dialog", { name: "删除会话" })).toBeVisible();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(sessionList.getByText("线上启动失败")).toHaveCount(0);

  await primaryNav.getByRole("button", { name: "特性", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "特性列表" }).getByText("支付结算"),
  ).toBeVisible();
  await page.getByRole("tab", { name: "关联仓库" }).click();
  await expect(page.getByRole("checkbox", { name: /codeask/ })).toBeVisible();

  await page.getByRole("button", { name: "未登录" }).click();
  await page.getByRole("menuitem", { name: "登录" }).click();
  await expect(page.getByRole("heading", { name: "登录" })).toBeVisible();
  await expect(page.getByText(/管理员/)).toHaveCount(0);
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admin");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await primaryNav.getByRole("button", { name: "设置", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "设置", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(/权限隔离后普通用户/)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "用户配置" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "全局配置" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "设置", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(/权限隔离后普通用户/)).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "全局 LLM 配置" }),
  ).toBeVisible();
  await expect(page.getByText("OpenAI 兼容")).toBeVisible();
});

test("global settings config forms align with analysis policy layout and keep list spacing", async ({
  page,
}) => {
  await installApiMocks(page);
  await page.goto("/");

  await page.getByRole("button", { name: "未登录" }).click();
  await page.getByRole("menuitem", { name: "登录" }).click();
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admin");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "设置", exact: true })
    .click();

  await page.getByRole("button", { name: "添加 LLM 配置" }).click();
  await page.getByRole("button", { name: "编辑 OpenAI 兼容" }).click();
  await page.getByRole("button", { name: "添加仓库" }).click();
  await page.getByRole("button", { name: "编辑仓库 codeask" }).click();
  await page.getByRole("button", { name: "添加分析策略" }).click();
  await page
    .getByRole("button", { name: "编辑分析策略 证据引用规范" })
    .click();

  const layout = await page.evaluate(() => {
    function sectionByTitle(title: string) {
      return Array.from(document.querySelectorAll("section.surface")).find(
        (section) => section.textContent?.includes(title),
      );
    }

    function formsInSection(title: string) {
      const section = sectionByTitle(title);
      const forms = Array.from(
        section?.querySelectorAll("form.inline-form") ?? [],
      );
      const list = section?.querySelector("ul.settings-config-list");
      return {
        createForm: forms.find((form) => !form.closest("li")),
        editForm: forms.find((form) => form.closest("li")),
        list,
      };
    }

    function rectOf(element: Element | undefined) {
      const rect = element?.getBoundingClientRect();
      return rect
        ? {
            bottom: rect.bottom,
            left: rect.left,
            top: rect.top,
            width: rect.width,
          }
        : null;
    }

    function createFormGap(sectionTitle: string) {
      const { createForm, list } = formsInSection(sectionTitle);
      const createRect = createForm?.getBoundingClientRect();
      const listRect = list?.getBoundingClientRect();
      const rowGap = list
        ? Number.parseFloat(getComputedStyle(list).rowGap)
        : Number.NaN;

      return createRect && listRect
        ? {
            gap: listRect.top - createRect.bottom,
            rowGap,
          }
        : null;
    }

    const llmForms = formsInSection("全局 LLM 配置");
    const repoForms = formsInSection("仓库管理");
    const policyForms = formsInSection("全局分析策略");
    const llmCreateRect = rectOf(llmForms.createForm);
    const llmEditRect = rectOf(llmForms.editForm);
    const repoCreateRect = rectOf(repoForms.createForm);
    const repoEditRect = rectOf(repoForms.editForm);
    const policyCreateRect = rectOf(policyForms.createForm);
    const policyEditRect = rectOf(policyForms.editForm);
    const llmSpacing = createFormGap("全局 LLM 配置");
    const repoSpacing = createFormGap("仓库管理");
    const policySpacing = createFormGap("全局分析策略");

    return llmCreateRect &&
      llmEditRect &&
      repoCreateRect &&
      repoEditRect &&
      policyCreateRect &&
      policyEditRect &&
      llmSpacing &&
      repoSpacing &&
      policySpacing
      ? {
          llmCreateLeft: llmCreateRect.left,
          llmCreateWidth: llmCreateRect.width,
          llmEditLeft: llmEditRect.left,
          llmEditWidth: llmEditRect.width,
          llmGap: llmSpacing.gap,
          policyCreateLeft: policyCreateRect.left,
          policyCreateWidth: policyCreateRect.width,
          policyEditLeft: policyEditRect.left,
          policyEditWidth: policyEditRect.width,
          policyGap: policySpacing.gap,
          policyListGap: policySpacing.rowGap,
          repoCreateLeft: repoCreateRect.left,
          repoCreateWidth: repoCreateRect.width,
          repoEditLeft: repoEditRect.left,
          repoEditWidth: repoEditRect.width,
          repoGap: repoSpacing.gap,
          repoListGap: repoSpacing.rowGap,
        }
      : null;
  });

  expect(layout).not.toBeNull();
  expect(layout!.repoGap).toBeCloseTo(layout!.repoListGap, 0);
  expect(layout!.llmGap).toBeCloseTo(layout!.repoListGap, 0);
  expect(layout!.policyGap).toBeCloseTo(layout!.repoListGap, 0);
  expect(layout!.policyListGap).toBeCloseTo(layout!.repoListGap, 0);
  for (const [left, width] of [
    [layout!.policyEditLeft, layout!.policyEditWidth],
    [layout!.repoCreateLeft, layout!.repoCreateWidth],
    [layout!.repoEditLeft, layout!.repoEditWidth],
    [layout!.llmCreateLeft, layout!.llmCreateWidth],
    [layout!.llmEditLeft, layout!.llmEditWidth],
  ]) {
    expect(Math.abs(left - layout!.policyCreateLeft)).toBeLessThanOrEqual(2);
    expect(Math.abs(width - layout!.policyCreateWidth)).toBeLessThanOrEqual(2);
  }
});

test("wiki import drawer keeps queue details visible across failure and unfinished close confirmation", async ({
  page,
}) => {
  await installApiMocks(page);
  await page.goto("/");

  const primaryNav = page.getByRole("navigation", { name: "主导航" });
  await primaryNav.getByRole("button", { name: "Wiki", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Wiki 目录树" })).toBeVisible();

  await page
    .getByRole("button", { name: "打开节点 知识库 的更多操作" })
    .click();
  await page.getByRole("menuitem", { name: "导入 Wiki" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  await page.getByLabel("选择 Markdown 文件").setInputFiles([
    {
      name: "Runbook-A.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Runbook A\n\nfirst upload fails"),
    },
    {
      name: "Runbook-B.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Runbook B\n\nsecond upload succeeds"),
    },
  ]);

  await expect(page.getByText("失败 1")).toBeVisible();
  await expect(page.getByText("已上传 1")).toBeVisible();
  await expect(page.getByRole("note").getByText("first upload failed")).toBeVisible();
  await expect(page.getByText("Runbook-B.md")).toBeVisible();

  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await expect(page.getByText("导入尚未完成")).toBeVisible();
  await page.getByRole("button", { name: "继续后台" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

async function installApiMocks(page: Page) {
  let isAdmin = false;
  let wikiImportStage: "initial" | "after_first_failure" | "after_second_uploaded" =
    "initial";
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = `${url.pathname}${url.search}`;
    const method = request.method();

    if (path === "/api/auth/me" && method === "GET") {
      return json(
        route,
        isAdmin
          ? {
              subject_id: "admin",
              display_name: "Admin",
              role: "admin",
              authenticated: true,
            }
          : {
              subject_id: "client_e2e",
              display_name: "client_e2e",
              role: "member",
              authenticated: false,
            },
      );
    }
    if (path === "/api/auth/admin/login" && method === "POST") {
      isAdmin = true;
      return json(route, {
        subject_id: "admin",
        display_name: "Admin",
        role: "admin",
        authenticated: true,
      });
    }
    if (path === "/api/auth/logout" && method === "POST") {
      isAdmin = false;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/sessions" && method === "GET") {
      return json(route, [
        {
          id: "sess_e2e",
          title: "线上启动失败",
          created_by_subject_id: "client_e2e",
          status: "active",
          pinned: false,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
      ]);
    }
    if (path === "/api/sessions/sess_e2e/messages" && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'event: stage_transition\ndata: {"stage":"knowledge_retrieval","label":"知识检索"}',
          'event: text_delta\ndata: {"delta":"需要检查启动配置。"}',
          'event: done\ndata: {"turn_id":"turn_e2e"}',
        ].join("\n\n"),
      });
    }
    if (path === "/api/sessions/sess_e2e/turns" && method === "GET") {
      return json(route, [
        {
          id: "turn_user_1",
          session_id: "sess_e2e",
          turn_index: 0,
          role: "user",
          content: "支付服务启动失败",
          evidence: null,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
        {
          id: "turn_e2e",
          session_id: "sess_e2e",
          turn_index: 1,
          role: "agent",
          content: "需要检查启动配置。",
          evidence: null,
          created_at: "2026-04-30T10:00:01",
          updated_at: "2026-04-30T10:00:01",
        },
      ]);
    }
    if (path === "/api/sessions/sess_e2e/traces" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/sessions/sess_e2e/attachments" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/sessions/sess_e2e" && method === "DELETE") {
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/features" && method === "GET") {
      return json(route, [feature]);
    }
    if (path === "/api/wiki/tree" && method === "GET") {
      return json(route, {
        space: null,
        nodes: [
          {
            id: -1,
            space_id: 0,
            feature_id: null,
            parent_id: null,
            type: "folder",
            name: "当前特性",
            path: "当前特性",
            system_role: "feature_group_current",
            sort_order: 0,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          {
            id: -2,
            space_id: 0,
            feature_id: null,
            parent_id: null,
            type: "folder",
            name: "历史特性",
            path: "历史特性",
            system_role: "feature_group_history",
            sort_order: 1,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          {
            id: -100007,
            space_id: 70,
            feature_id: 7,
            parent_id: -1,
            type: "folder",
            name: "支付结算",
            path: "当前特性/payment-settlement",
            system_role: "feature_space_current",
            sort_order: 0,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          {
            id: 701,
            space_id: 70,
            feature_id: 7,
            parent_id: -100007,
            type: "folder",
            name: "知识库",
            path: "knowledge-base",
            system_role: "knowledge_base",
            sort_order: 100,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ],
      });
    }
    if (path === "/api/wiki/spaces/by-feature/7" && method === "GET") {
      return json(route, {
        id: 70,
        feature_id: 7,
        scope: "current",
        display_name: "支付结算",
        slug: "payment-settlement",
        status: "ready",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00",
      });
    }
    if (path === "/api/wiki/reports/projections?feature_id=7" && method === "GET") {
      return json(route, { items: [] });
    }
    if (path === "/api/wiki/import-sessions" && method === "POST") {
      return json(
        route,
        {
          id: 401,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "running",
          requested_by_subject_id: "client_e2e",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 2,
            pending_count: 2,
            uploading_count: 0,
            uploaded_count: 0,
            conflict_count: 0,
            failed_count: 0,
            ignored_count: 0,
            skipped_count: 0,
          },
        },
        201,
      );
    }
    if (path === "/api/wiki/import-sessions/401/scan" && method === "POST") {
      return json(route, {
        id: 401,
        space_id: 70,
        parent_id: 701,
        mode: "markdown",
        status: "running",
        requested_by_subject_id: "client_e2e",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00",
        summary: {
          total_files: 2,
          pending_count: 2,
          uploading_count: 0,
          uploaded_count: 0,
          conflict_count: 0,
          failed_count: 0,
          ignored_count: 0,
          skipped_count: 0,
        },
      });
    }
    if (path === "/api/wiki/import-sessions/401" && method === "GET") {
      return json(route, currentImportSessionSummary(wikiImportStage));
    }
    if (path === "/api/wiki/import-sessions/401/items" && method === "GET") {
      return json(route, { items: currentImportItems(wikiImportStage) });
    }
    if (path === "/api/wiki/import-sessions/401/items/1/upload" && method === "POST") {
      wikiImportStage = "after_first_failure";
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "first upload failed" }),
      });
    }
    if (path === "/api/wiki/import-sessions/401/items/2/upload" && method === "POST") {
      wikiImportStage = "after_second_uploaded";
      return json(route, {
        session: currentImportSessionSummary(wikiImportStage),
        item: currentImportItems(wikiImportStage)[1],
      });
    }
    if (path === "/api/documents?feature_id=7" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/reports?feature_id=7" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/features/7/repos" && method === "GET") {
      return json(route, { repos: [repo] });
    }
    if (path === "/api/repos" && method === "GET") {
      return json(route, { repos: [repo] });
    }
    if (path === "/api/skills" && method === "GET") {
      return json(route, [globalPolicy]);
    }
    if (path === "/api/me/llm-configs" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/admin/llm-configs" && method === "GET") {
      return json(route, [
        {
          id: "llm_e2e",
          name: "OpenAI 兼容",
          scope: "global",
          owner_subject_id: null,
          protocol: "openai_compatible",
          base_url: "http://llm.internal/v1",
          api_key_masked: "sk-...e2e",
          model_name: "qwen3-coder",
          max_tokens: 4096,
          temperature: 0.2,
          is_default: true,
          enabled: true,
          rpm_limit: null,
          quota_remaining: null,
        },
      ]);
    }

    throw new Error(`Unexpected ${method} ${path}`);
  });
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function currentImportSessionSummary(stage: "initial" | "after_first_failure" | "after_second_uploaded") {
  if (stage === "after_second_uploaded") {
    return {
      id: 401,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 1,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_first_failure") {
    return {
      id: 401,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 1,
        uploading_count: 0,
        uploaded_count: 0,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  return {
    id: 401,
    space_id: 70,
    parent_id: 701,
    mode: "markdown",
    status: "running",
    requested_by_subject_id: "client_e2e",
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
    summary: {
      total_files: 2,
      pending_count: 2,
      uploading_count: 0,
      uploaded_count: 0,
      conflict_count: 0,
      failed_count: 0,
      ignored_count: 0,
      skipped_count: 0,
    },
  };
}

function currentImportItems(stage: "initial" | "after_first_failure" | "after_second_uploaded") {
  return [
    {
      id: 1,
      source_path: "Runbook-A.md",
      target_path: "knowledge-base/runbook-a",
      item_kind: "document",
      status: stage === "initial" ? "pending" : "failed",
      progress_percent: stage === "initial" ? 0 : 100,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_401/Runbook-A.md",
      result_node_id: null,
      error_message: stage === "initial" ? null : "first upload failed",
    },
    {
      id: 2,
      source_path: "Runbook-B.md",
      target_path: "knowledge-base/runbook-b",
      item_kind: "document",
      status: stage === "after_second_uploaded" ? "uploaded" : "pending",
      progress_percent: stage === "after_second_uploaded" ? 100 : 0,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_401/Runbook-B.md",
      result_node_id: stage === "after_second_uploaded" ? 706 : null,
      error_message: null,
    },
  ];
}
