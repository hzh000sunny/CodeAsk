import { expect, test, type Page, type Route } from "@playwright/test";

test("refreshes session list immediately after logging in as admin", async ({
  page,
}) => {
  await installAuthSessionSwitchMocks(page);
  await page.goto("/#/sessions");

  const sessionsRegion = page.getByRole("region", { name: "会话列表" });
  await expect(sessionsRegion.getByText("普通用户会话")).toBeVisible();

  await page.getByRole("button", { name: "未登录" }).click();
  await page.getByRole("menuitem", { name: "登录" }).click();
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admin");
  await page.getByRole("button", { name: "登录", exact: true }).click();

  await expect(page.getByRole("button", { name: "Admin", exact: true })).toBeVisible();
  await expect(sessionsRegion.getByText("管理员会话")).toBeVisible();
  await expect(sessionsRegion.getByText("普通用户会话")).toHaveCount(0);

  await page.getByRole("button", { name: "Admin", exact: true }).click();
  await page.getByRole("menuitem", { name: "退出" }).click();

  await expect(page.getByRole("button", { name: "未登录" })).toBeVisible();
  await expect(sessionsRegion.getByText("普通用户会话")).toBeVisible();
  await expect(sessionsRegion.getByText("管理员会话")).toHaveCount(0);
});

async function installAuthSessionSwitchMocks(page: Page) {
  let authenticated = false;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = `${url.pathname}${url.search}`;
    const method = request.method();

    if (path === "/api/healthz") {
      return json(route, { status: "ok" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return json(
        route,
        authenticated
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
      authenticated = true;
      return json(route, {
        subject_id: "admin",
        display_name: "Admin",
        role: "admin",
        authenticated: true,
      });
    }
    if (path === "/api/auth/logout" && method === "POST") {
      authenticated = false;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/sessions" && method === "GET") {
      return json(route, [
        authenticated
          ? session("sess_admin", "管理员会话", "admin")
          : session("sess_member", "普通用户会话", "client_e2e"),
      ]);
    }
    if (path.match(/^\/api\/sessions\/[^/]+\/turns$/) && method === "GET") {
      return json(route, []);
    }
    if (path.match(/^\/api\/sessions\/[^/]+\/traces$/) && method === "GET") {
      return json(route, []);
    }
    if (
      path.match(/^\/api\/sessions\/[^/]+\/attachments$/) &&
      method === "GET"
    ) {
      return json(route, []);
    }
    if (path === "/api/features" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/admin/llm-configs" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/repos" && method === "GET") {
      return json(route, { repos: [] });
    }
    if (path === "/api/skills" && method === "GET") {
      return json(route, []);
    }

    return json(route, {});
  });
}

function session(id: string, title: string, subjectId: string) {
  return {
    id,
    title,
    created_by_subject_id: subjectId,
    status: "active",
    pinned: false,
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
  };
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
