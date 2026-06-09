import { expect, test, type Page, type Route } from "@playwright/test";

// 特性设置页「可编辑名称/描述」端到端验证：
// admin 登录 → 特性页设置 tab → 改名/改描述 → 保存走 PUT → 列表与报头刷出新名。
// 通过 page.route 拦截 /api/**，前端跑的是真实构建产物。

const baseFeature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_e2e",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

test("admin edits feature name and description from the settings tab", async ({
  page,
}) => {
  const putBodies: Array<Record<string, unknown>> = [];
  await installFeatureMocks(page, putBodies);
  await page.goto("/");

  await loginMockAdmin(page);

  await page
    .getByRole("navigation", { name: "主导航" })
    .getByRole("button", { name: "特性", exact: true })
    .click();

  // 设置 tab 默认选中：admin 看到的是真实可编辑输入框（而非旧的只读假框）。
  const nameInput = page.getByRole("textbox", { name: "名称", exact: true });
  await expect(nameInput).toHaveValue("支付结算");
  const descriptionInput = page.getByRole("textbox", { name: "描述", exact: true });
  await expect(descriptionInput).toHaveValue("支付链路知识域");

  // 未改动时保存禁用。
  const saveButton = page.getByRole("button", { name: "保存修改" });
  await expect(saveButton).toBeDisabled();

  await nameInput.fill("支付结算中心");
  await descriptionInput.fill("支付链路与对账知识域");
  await expect(saveButton).toBeEnabled();
  await saveButton.click();

  // 保存走 PUT /api/features/7，携带新名与新描述。
  await expect.poll(() => putBodies.length).toBeGreaterThan(0);
  expect(putBodies[0]).toMatchObject({
    name: "支付结算中心",
    description: "支付链路与对账知识域",
  });

  // 刷新后列表与报头都反映新名（slug 不变，仍是同一条）。
  await expect(
    page.getByRole("region", { name: "特性列表" }).getByText("支付结算中心"),
  ).toBeVisible();
  await expect(
    page.locator(".feature-header h1", { hasText: "支付结算中心" }),
  ).toBeVisible();
});

async function loginMockAdmin(page: Page) {
  await page.getByRole("button", { name: "未登录" }).click();
  await page.getByRole("menuitem", { name: "登录" }).click();
  await page.getByLabel("用户名").fill("admin");
  await page.getByLabel("密码", { exact: true }).fill("admin");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Admin", exact: true }),
  ).toBeVisible();
}

async function installFeatureMocks(
  page: Page,
  putBodies: Array<Record<string, unknown>>,
) {
  let isAdmin = false;
  const featureRow: Record<string, unknown> = { ...baseFeature };

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
    if (
      (path === "/api/auth/admin/login" || path === "/api/auth/login") &&
      method === "POST"
    ) {
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
      return json(route, []);
    }
    if (path === "/api/features" && method === "GET") {
      return json(route, [featureRow]);
    }
    if (path === "/api/features/7" && method === "PUT") {
      const body = JSON.parse(request.postData() ?? "{}") as {
        name?: string;
        description?: string;
      };
      putBodies.push(body);
      if (typeof body.name === "string") {
        featureRow.name = body.name;
      }
      if (typeof body.description === "string") {
        featureRow.description = body.description;
      }
      featureRow.updated_at = "2026-04-30T12:00:00";
      return json(route, featureRow);
    }
    if (path === "/api/features/7/admins" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/documents?feature_id=7" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/reports?feature_id=7" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/wiki/reports/projections?feature_id=7" && method === "GET") {
      return json(route, { items: [] });
    }
    if (path === "/api/features/7/repos" && method === "GET") {
      return json(route, { repos: [] });
    }
    if (path === "/api/repos" && method === "GET") {
      return json(route, { repos: [] });
    }
    if (path === "/api/skills" && method === "GET") {
      return json(route, []);
    }

    // 设置 tab 以外的依赖（wiki 树等）按需返回空，避免未匹配抛错让用例脆弱。
    if (method === "GET") {
      return json(route, {});
    }
    return route.fulfill({ status: 204 });
  });
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
