import { expect, test, type Page, type Route } from "@playwright/test";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_e2e",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00"
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
  updated_at: "2026-04-30T10:00:00"
};

test("source-list workbench happy path", async ({ page }) => {
  await installApiMocks(page);
  await page.goto("/");

  const primaryNav = page.getByRole("navigation", { name: "主导航" });
  await expect(primaryNav).toBeVisible();
  await expect(primaryNav.getByRole("button", { name: "会话", exact: true })).toHaveAttribute("aria-current", "page");

  await page.getByRole("textbox", { name: "会话输入" }).fill("支付服务启动失败");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("需要检查启动配置。")).toBeVisible();
  await expect(page.getByRole("region", { name: "调查进度" }).getByText("知识检索")).toBeVisible();
  const sessionList = page.getByRole("region", { name: "会话列表" });
  await sessionList.getByRole("button", { name: "打开会话 线上启动失败 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "删除" }).click();
  await expect(page.getByRole("dialog", { name: "删除会话" })).toBeVisible();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(sessionList.getByText("线上启动失败")).toHaveCount(0);

  await primaryNav.getByRole("button", { name: "特性", exact: true }).click();
  await expect(page.getByRole("region", { name: "特性列表" }).getByText("支付结算")).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toHaveCount(0);
  await expect(page.getByText(/权限隔离后普通用户/)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "用户配置" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "全局配置" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toHaveCount(0);
  await expect(page.getByText(/权限隔离后普通用户/)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "全局 LLM 配置" })).toBeVisible();
  await expect(page.getByText("OpenAI 兼容")).toBeVisible();
});

async function installApiMocks(page: Page) {
  let isAdmin = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = `${url.pathname}${url.search}`;
    const method = request.method();

    if (path === "/api/auth/me" && method === "GET") {
      return json(route, isAdmin ? {
        subject_id: "admin",
        display_name: "Admin",
        role: "admin",
        authenticated: true
      } : {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        role: "member",
        authenticated: false
      });
    }
    if (path === "/api/auth/admin/login" && method === "POST") {
      isAdmin = true;
      return json(route, {
        subject_id: "admin",
        display_name: "Admin",
        role: "admin",
        authenticated: true
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
          updated_at: "2026-04-30T10:00:00"
        }
      ]);
    }
    if (path === "/api/sessions/sess_e2e/messages" && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          'event: stage_transition\ndata: {"stage":"knowledge_retrieval","label":"知识检索"}',
          'event: text_delta\ndata: {"delta":"需要检查启动配置。"}',
          'event: done\ndata: {"turn_id":"turn_e2e"}'
        ].join("\n\n")
      });
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
      return json(route, []);
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
          quota_remaining: null
        }
      ]);
    }

    throw new Error(`Unexpected ${method} ${path}`);
  });
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload)
  });
}
