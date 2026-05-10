import { expect, test, type Page } from "@playwright/test";

type ApiResult<T = unknown> = {
  body: T;
  status: number;
};

type Feature = {
  id: number;
  name: string;
  slug: string;
};

type AuthMe = {
  authenticated: boolean;
  display_name: string;
  role: string;
  subject_id: string;
};

type WikiTree = {
  space: { id: number } | null;
  nodes: Array<{
    id: number;
    name: string;
    parent_id: number | null;
    path: string;
    space_id: number;
    system_role: string | null;
    type: string;
  }>;
};

test.describe("v1.0.3 auth access control", () => {
  test("anonymous, member, and admin session ownership rules work in browser", async ({
    page,
  }) => {
    const suffix = uniqueSuffix();
    await openAppWithSubject(page, `client_migrate_${suffix}`);

    const anonymousSession = await api<{ id: string; title: string }>(
      page,
      "/api/sessions",
      {
        method: "POST",
        body: { title: `匿名迁移会话 ${suffix}` },
      },
    );
    expect(anonymousSession.status).toBe(201);

    const member = await login(page, `member_${suffix}`, "memberPass1");
    expect(member.body.authenticated).toBe(true);
    expect(member.body.role).toBe("member");

    const migratedSessions = await api<Array<{ id: string; title: string }>>(
      page,
      "/api/sessions",
    );
    expect(migratedSessions.body.map((item) => item.id)).toContain(
      anonymousSession.body.id,
    );

    await logout(page);
    await openAppWithSubject(page, `client_admin_nomigrate_${suffix}`);
    const adminAnonymousSession = await api<{ id: string }>(
      page,
      "/api/sessions",
      {
        method: "POST",
        body: { title: `admin 不迁移会话 ${suffix}` },
      },
    );
    expect(adminAnonymousSession.status).toBe(201);

    const admin = await login(page, "admin", "admin");
    expect(admin.body.role).toBe("admin");
    const adminSessions = await api<Array<{ id: string }>>(page, "/api/sessions");
    expect(adminSessions.body.map((item) => item.id)).not.toContain(
      adminAnonymousSession.body.id,
    );

    await logout(page);
    await page.reload();
    const sessionsRegion = page.getByRole("region", { name: "会话列表" });
    await page.getByRole("button", { name: "新建会话" }).click();
    await expect(sessionsRegion.getByText("新的研发会话")).toBeVisible();
  });

  test("feature and wiki write permissions are enforced by real backend", async ({
    page,
  }) => {
    const suffix = uniqueSuffix();
    await openAppWithSubject(page, `client_authz_${suffix}`);

    const anonymousFeatureWrite = await api(page, "/api/features", {
      method: "POST",
      body: { name: `匿名特性 ${suffix}` },
    });
    expect(anonymousFeatureWrite.status).toBe(403);

    const member = await login(page, `feature_admin_${suffix}`, "memberPass1");
    const memberUserId = member.body.subject_id;
    await logout(page);

    await login(page, "admin", "admin");
    const managedFeature = await createFeature(page, `授权特性 ${suffix}`);
    const otherFeature = await createFeature(page, `未授权特性 ${suffix}`);
    const managedTree = await wikiTree(page, managedFeature.body.id);
    const otherTree = await wikiTree(page, otherFeature.body.id);
    const managedKnowledgeBase = requiredNode(managedTree.body, "knowledge_base");
    const otherKnowledgeBase = requiredNode(otherTree.body, "knowledge_base");

    await logout(page);
    await openAppWithSubject(page, `client_wiki_forbidden_${suffix}`);
    const anonymousWikiWrite = await api(page, "/api/wiki/nodes", {
      method: "POST",
      body: {
        name: `匿名 Wiki ${suffix}`,
        parent_id: managedKnowledgeBase.id,
        space_id: managedKnowledgeBase.space_id,
        type: "document",
      },
    });
    expect(anonymousWikiWrite.status).toBe(403);

    await login(page, "admin", "admin");
    const addAdmin = await api(page, `/api/features/${managedFeature.body.id}/admins`, {
      method: "POST",
      body: { user_id: memberUserId },
    });
    expect(addAdmin.status).toBe(201);
    await logout(page);

    await login(page, `feature_admin_${suffix}`, "memberPass1");
    const allowedWikiWrite = await api(page, "/api/wiki/nodes", {
      method: "POST",
      body: {
        name: `授权 Wiki ${suffix}`,
        parent_id: managedKnowledgeBase.id,
        space_id: managedKnowledgeBase.space_id,
        type: "document",
      },
    });
    expect(allowedWikiWrite.status).toBe(201);

    const forbiddenWikiWrite = await api(page, "/api/wiki/nodes", {
      method: "POST",
      body: {
        name: `未授权 Wiki ${suffix}`,
        parent_id: otherKnowledgeBase.id,
        space_id: otherKnowledgeBase.space_id,
        type: "document",
      },
    });
    expect(forbiddenWikiWrite.status).toBe(403);

    const featureAdminCannotManageAdmins = await api(
      page,
      `/api/features/${managedFeature.body.id}/admins/${memberUserId}`,
      { method: "DELETE" },
    );
    expect(featureAdminCannotManageAdmins.status).toBe(403);
  });

  test("admin UI manages features, feature admins, and attachment gate", async ({
    page,
  }) => {
    const suffix = uniqueSuffix();
    await openAppWithSubject(page, `client_ui_${suffix}`);

    await login(page, `candidate_${suffix}`, "memberPass1");
    const candidate = await api<AuthMe>(page, "/api/auth/me");
    await logout(page);

    await page.goto("/#/features");
    await page.getByRole("button", { name: "添加特性" }).click();
    await expect(
      page.getByRole("alertdialog", { name: "无权创建特性" }),
    ).toBeVisible();
    await expect(page.getByText("请联系管理员添加")).toBeVisible();
    await page.getByRole("button", { name: "知道了" }).click();

    await login(page, "admin", "admin");
    await page.goto(`/?ui=${suffix}#/features`);
    await page.getByRole("button", { name: "添加特性" }).click();
    await page.getByPlaceholder("例如：风控策略").fill(`UI 鉴权特性 ${suffix}`);
    await page.getByPlaceholder("补充边界、负责人和常见问题").fill("E2E 权限边界验证");
    await page.getByRole("button", { name: "创建特性" }).click();
    await expect(page.getByRole("heading", { name: `UI 鉴权特性 ${suffix}` })).toBeVisible();

    await page.getByRole("tab", { name: "管理员" }).click();
    await page.getByLabel("搜索可添加用户").fill(`candidate_${suffix}`);
    await page.getByRole("button", { name: `添加 candidate_${suffix}` }).click();
    await expect(page.getByText("特性管理员已添加")).toBeVisible();
    await expect(page.getByText(`candidate_${suffix}`)).toBeVisible();
    await page
      .getByRole("button", { name: `移除管理员 candidate_${suffix}` })
      .click();
    await expect(page.getByText("特性管理员已移除")).toBeVisible();

    await page.goto("/#/settings");
    await expect(page.getByRole("button", { name: "全局配置" })).toBeVisible();
    await page.getByText("允许上传附件").click();
    await expect(page.getByText("全局配置已保存")).toBeVisible();

    await logout(page);
    await openAppWithSubject(page, `client_upload_disabled_${suffix}`);
    const session = await api<{ id: string }>(page, "/api/sessions", {
      method: "POST",
      body: { title: `附件禁用会话 ${suffix}` },
    });
    const upload = await uploadAttachment(page, session.body.id);
    expect(upload.status).toBe(403);
    expect(JSON.stringify(upload.body)).toContain("该功能已被禁用");

    await login(page, "admin", "admin");
    const passwordClear = await api(
      page,
      `/api/users/${candidate.body.subject_id}/password/clear`,
      { method: "POST" },
    );
    expect(passwordClear.status).toBe(200);
  });
});

async function openAppWithSubject(page: Page, subjectId: string) {
  await page.goto("/");
  await page.evaluate((value) => {
    localStorage.setItem("codeask.subject_id", value);
  }, subjectId);
}

async function login(page: Page, username: string, password: string) {
  return api<AuthMe>(page, "/api/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

async function logout(page: Page) {
  await api(page, "/api/auth/logout", { method: "POST" });
}

async function createFeature(page: Page, name: string) {
  return api<Feature>(page, "/api/features", {
    method: "POST",
    body: {
      description: "E2E auth access control",
      name,
    },
  });
}

async function wikiTree(page: Page, featureId: number) {
  return api<WikiTree>(page, `/api/wiki/tree?feature_id=${featureId}`);
}

function requiredNode(tree: WikiTree, systemRole: string) {
  const node = tree.nodes.find((item) => item.system_role === systemRole);
  if (!node) {
    throw new Error(`missing wiki node ${systemRole}`);
  }
  return node;
}

async function uploadAttachment(page: Page, sessionId: string) {
  return page.evaluate(async (targetSessionId) => {
    async function readBody(response: Response) {
      const contentType = response.headers.get("Content-Type") ?? "";
      if (contentType.includes("application/json")) {
        return response.json();
      }
      return response.text();
    }

    const subjectId = localStorage.getItem("codeask.subject_id") ?? "client_e2e";
    const body = new FormData();
    body.set(
      "file",
      new File(["auth e2e"], "auth-e2e.log", { type: "text/plain" }),
    );
    body.set("kind", "log");
    const response = await fetch(`/api/sessions/${targetSessionId}/attachments`, {
      body,
      credentials: "same-origin",
      headers: {
        "X-Subject-Id": subjectId,
      },
      method: "POST",
    });
    return {
      body: await readBody(response),
      status: response.status,
    };
  }, sessionId);
}

async function api<T = unknown>(
  page: Page,
  path: string,
  init: { body?: unknown; method?: string } = {},
): Promise<ApiResult<T>> {
  return page.evaluate(
    async ({ body, method, path }) => {
      async function readBody(response: Response) {
        const contentType = response.headers.get("Content-Type") ?? "";
        if (contentType.includes("application/json")) {
          return response.json();
        }
        return response.text();
      }

      const headers: Record<string, string> = {
        "X-Subject-Id": localStorage.getItem("codeask.subject_id") ?? "client_e2e",
      };
      let requestBody: string | undefined;
      if (body !== undefined) {
        headers["Content-Type"] = "application/json";
        requestBody = JSON.stringify(body);
      }
      const response = await fetch(path, {
        body: requestBody,
        credentials: "same-origin",
        headers,
        method: method ?? "GET",
      });
      return {
        body: (await readBody(response)) as T,
        status: response.status,
      };
    },
    { body: init.body, method: init.method, path },
  );
}

function uniqueSuffix() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
