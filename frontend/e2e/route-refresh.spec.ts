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

test("keeps the current top-level page after browser reload", async ({ page }) => {
  await installRouteRefreshApiMocks(page);

  await page.goto("/#/sessions");
  await expect(page.getByPlaceholder("搜索会话")).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("搜索会话")).toBeVisible();
  await expect(page).toHaveURL(/#\/sessions$/);

  await page.goto("/#/features");
  await expect(page.getByPlaceholder("搜索特性")).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("搜索特性")).toBeVisible();
  await expect(page).toHaveURL(/#\/features$/);

  await page.goto("/#/wiki");
  await expect(page.getByText("当前特性")).toBeVisible();
  await page.reload();
  await expect(page.getByText("当前特性")).toBeVisible();
  await expect(page).toHaveURL(/#\/wiki\?feature=7$/);

  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "用户配置" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "用户配置" })).toBeVisible();
  await expect(page).toHaveURL(/#\/settings$/);
});

async function installRouteRefreshApiMocks(page: Page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = `${url.pathname}${url.search}`;

    if (path === "/api/healthz") {
      return json(route, { status: "ok" });
    }
    if (path === "/api/auth/me") {
      return json(route, {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        role: "member",
        authenticated: false,
      });
    }
    if (path === "/api/sessions") {
      return json(route, []);
    }
    if (path === "/api/features") {
      return json(route, [feature]);
    }
    if (path === "/api/me") {
      return json(route, {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        nickname: "client_e2e",
      });
    }
    if (path === "/api/me/llm-configs") {
      return json(route, []);
    }
    if (path === "/api/llm-configs") {
      return json(route, []);
    }
    if (path === "/api/repos") {
      return json(route, { repos: [] });
    }
    if (path === "/api/analysis-policies") {
      return json(route, []);
    }
    if (path === "/api/wiki/search?q=&limit=20") {
      return json(route, { items: [] });
    }
    if (path === "/api/wiki/tree") {
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
            sort_order: 0,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          {
            id: 702,
            space_id: 70,
            feature_id: 7,
            parent_id: -100007,
            type: "folder",
            name: "问题定位报告",
            path: "reports",
            system_role: "reports",
            sort_order: 1,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ],
      });
    }

    return json(route, {});
  });
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
