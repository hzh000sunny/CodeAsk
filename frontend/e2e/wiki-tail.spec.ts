import { expect, test, type Page, type Route } from "@playwright/test";

const NOW = "2026-05-06T09:00:00";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_e2e",
  summary_text: null,
  created_at: NOW,
  updated_at: NOW,
};

const currentSpace = {
  id: 70,
  feature_id: 7,
  scope: "current",
  display_name: "支付结算",
  slug: "payment-settlement",
  status: "ready",
  created_at: NOW,
  updated_at: NOW,
};

const archivedSpace = {
  id: 71,
  feature_id: 8,
  scope: "history",
  display_name: "历史支付",
  slug: "history-payment",
  status: "archived",
  created_at: NOW,
  updated_at: NOW,
};

test("wiki sources drawer supports create, edit and sync in browser flow", async ({ page }) => {
  const state = {
    documentTitle: "支付回调手册",
    sources: [
      buildWikiSource({
        id: 801,
        display_name: "上线手册导入",
        kind: "directory_import",
        last_synced_at: null,
        metadata_json: { root_path: "docs/runbooks/payment" },
        uri: "file:///srv/wiki/payment",
      }),
    ],
  };

  await installWikiTailMocks(page, {
    state,
    async onRoute({ method, path, request, route }) {
      if (path === "/api/wiki/sources?space_id=70" && method === "GET") {
        await json(route, { items: state.sources });
        return true;
      }
      if (path === "/api/wiki/sources" && method === "POST") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        const created = buildWikiSource({
          id: 802,
          display_name: String(payload.display_name),
          kind: String(payload.kind) as "directory_import" | "manual_upload" | "session_promotion",
          last_synced_at: null,
          metadata_json: (payload.metadata_json as Record<string, unknown> | null) ?? null,
          uri: (payload.uri as string | null) ?? null,
        });
        state.sources = [...state.sources, created];
        await json(route, created, 201);
        return true;
      }
      if (path === "/api/wiki/sources/801" && method === "PUT") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        state.sources = state.sources.map((source) =>
          source.id === 801
            ? {
                ...source,
                display_name: String(payload.display_name ?? source.display_name),
                metadata_json:
                  (payload.metadata_json as Record<string, unknown> | null) ?? source.metadata_json,
                updated_at: "2026-05-06T09:15:00",
              }
            : source,
        );
        await json(route, state.sources.find((source) => source.id === 801));
        return true;
      }
      if (path === "/api/wiki/sources/801/sync" && method === "POST") {
        state.sources = state.sources.map((source) =>
          source.id === 801
            ? {
                ...source,
                last_synced_at: "2026-05-06T09:20:00",
                updated_at: "2026-05-06T09:20:00",
              }
            : source,
        );
        await json(route, state.sources.find((source) => source.id === 801));
        return true;
      }
      return false;
    },
  });

  await page.goto("/#/wiki?feature=7&node=703");

  await page.locator(".wiki-floating-actions").getByRole("button", { name: "更多" }).click();
  await page.getByRole("menuitem", { name: "来源治理" }).click();
  const drawer = page.getByRole("dialog", { name: "来源治理" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("上线手册导入")).toBeVisible();

  await drawer.getByRole("button", { name: "添加来源" }).click();
  await drawer.getByLabel("来源名称").fill("会话沉淀");
  await drawer.getByLabel("来源类型").selectOption("session_promotion");
  await drawer.getByLabel("URI / 路径").fill("session://sess_e2e/attach_1");
  await drawer.getByRole("button", { name: "保存来源" }).click();

  await expect(drawer.getByText("会话沉淀")).toBeVisible();
  await expect(page.getByText("来源已创建")).toBeVisible();

  await drawer.locator("[data-testid='wiki-source-row-801']").getByRole("button", { name: "编辑来源" }).click();
  await drawer.getByLabel("来源名称").fill("上线手册导入-已更新");
  await drawer.getByRole("button", { name: "保存来源" }).click();
  await expect(drawer.getByText("上线手册导入-已更新")).toBeVisible();
  await expect(page.getByText("来源已更新")).toBeVisible();

  await drawer.locator("[data-testid='wiki-source-row-801']").getByRole("button", { name: "同步来源" }).click();
  await expect(drawer.getByText("刚刚同步")).toBeVisible();
  await expect(page.getByText("来源同步成功")).toBeVisible();
});

test("wiki restore and reindex entrypoints stay usable in browser flow", async ({ page }) => {
  const state = {
    archivedVisible: true,
    documentDeleted: false,
    documentTitle: "支付回调手册",
  };

  await installWikiTailMocks(page, {
    authRole: "admin",
    state,
    onRoute({ method, path, route }) {
      if (path === "/api/wiki/nodes/703" && method === "DELETE") {
        state.documentDeleted = true;
        return route.fulfill({ status: 204, body: "" }).then(() => true);
      }
      if (path === "/api/wiki/nodes/703/restore" && method === "POST") {
        state.documentDeleted = false;
        return json(route, buildDocumentNode()).then(() => true);
      }
      if (path === "/api/wiki/maintenance/nodes/701/reindex" && method === "POST") {
        return json(route, { root_node_id: 701, reindexed_documents: 2 }).then(() => true);
      }
      if (path === "/api/wiki/spaces/71/restore" && method === "POST") {
        state.archivedVisible = false;
        return json(route, archivedSpace).then(() => true);
      }
      return false;
    },
  });

  await page.goto("/#/wiki?feature=7&node=703");

  await page.getByRole("button", { name: "打开节点 支付回调手册 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "删除" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();

  const restoreDialog = page.getByRole("dialog", { name: "Wiki 节点已删除，可恢复" });
  await expect(restoreDialog).toBeVisible();
  await restoreDialog.getByRole("button", { name: "恢复节点" }).click();
  await expect(page.getByText("Wiki 节点已恢复")).toBeVisible();
  await expect(page).toHaveURL(/#\/wiki\?feature=7&node=703$/);

  await page.getByRole("button", { name: "打开节点 知识库 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "重新索引" }).click();
  await page.getByRole("button", { name: "确认重新索引" }).click();
  await expect(page.getByText("已重新索引 2 篇文档")).toBeVisible();

  await page.getByRole("button", { name: "历史特性" }).click();
  await page.getByRole("button", { name: "打开节点 历史支付 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "恢复特性" }).click();
  await page.getByRole("button", { name: "确认恢复" }).click();
  await expect(page.getByText("历史特性已恢复")).toBeVisible();
  await expect(page.getByText("历史支付")).toHaveCount(0);
});

test("session attachment promotion can jump from session into target wiki node", async ({
  page,
}) => {
  const state = {
    documentTitle: "启动排查记录",
  };

  await installWikiTailMocks(page, {
    sessionAttachmentName: "启动排查记录.md",
    sessionAttachmentKind: "doc",
    state,
    onRoute({ method, path, request, route }) {
      if (path === "/api/wiki/promotions/session-attachment" && method === "POST") {
        const payload = request.postDataJSON() as Record<string, unknown>;
        state.documentTitle = String(payload.name ?? "启动排查记录");
        return json(route, {
          node: {
            ...buildDocumentNode(),
            name: state.documentTitle,
          },
          document_id: 9001,
          source_id: 8801,
        }).then(() => true);
      }
      return false;
    },
  });

  await page.goto("/#/sessions");

  const attachmentRegion = page.getByRole("region", { name: "会话数据" });
  await expect(attachmentRegion.getByText("启动排查记录.md")).toBeVisible();
  await attachmentRegion.getByRole("button", { name: "晋级为 Wiki 启动排查记录.md" }).click();

  const dialog = page.getByRole("dialog", { name: "晋级为 Wiki" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("目标特性")).toHaveValue("7");
  await expect(dialog.getByLabel("目标目录")).not.toHaveValue("");
  await dialog.getByLabel("Wiki 标题").fill("启动排查记录");
  await dialog.getByRole("button", { name: "确认晋级" }).click();

  const successDialog = page.getByRole("dialog", { name: "已写入 Wiki" });
  await expect(successDialog).toBeVisible();
  await successDialog.getByRole("button", { name: "打开 Wiki" }).click();

  await expect(page).toHaveURL(/#\/wiki\?feature=7&node=703$/);
  await expect(page.locator(".wiki-page-header h1")).toHaveText("启动排查记录");
});

async function installWikiTailMocks(
  page: Page,
  options: {
    authRole?: "member" | "admin";
    onRoute?: (context: {
      method: string;
      path: string;
      request: ReturnType<Page["request"]["get"]> extends never ? never : any;
      route: Route;
      url: URL;
    }) => Promise<boolean | void> | boolean | void;
    sessionAttachmentKind?: "log" | "image" | "doc" | "other";
    sessionAttachmentName?: string;
    state: {
      archivedVisible?: boolean;
      documentDeleted?: boolean;
      documentTitle: string;
      sources?: Array<ReturnType<typeof buildWikiSource>>;
    };
  },
) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = `${url.pathname}${url.search}`;
    const method = request.method();

    const customResult = await options.onRoute?.({ method, path, request, route, url });
    if (customResult) {
      return;
    }

    if (path === "/api/healthz" && method === "GET") {
      return json(route, { status: "ok" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return json(route, {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        role: options.authRole ?? "member",
        authenticated: options.authRole === "admin",
      });
    }
    if (path === "/api/me" && method === "GET") {
      return json(route, {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        nickname: "client_e2e",
      });
    }
    if (path === "/api/features" && method === "GET") {
      return json(route, [feature]);
    }
    if (path === "/api/me/llm-configs" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/sessions" && method === "GET") {
      return json(route, [
        {
          id: "sess_e2e",
          title: "线上启动失败",
          created_by_subject_id: "client_e2e",
          status: "active",
          pinned: false,
          created_at: NOW,
          updated_at: NOW,
        },
      ]);
    }
    if (path === "/api/sessions/sess_e2e/turns" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/sessions/sess_e2e/traces" && method === "GET") {
      return json(route, []);
    }
    if (path === "/api/sessions/sess_e2e/attachments" && method === "GET") {
      return json(route, [
        {
          id: "attach_1",
          session_id: "sess_e2e",
          kind: options.sessionAttachmentKind ?? "doc",
          display_name: options.sessionAttachmentName ?? "启动排查记录.md",
          original_filename: options.sessionAttachmentName ?? "启动排查记录.md",
          aliases: [],
          reference_names: [],
          description: "启动阶段的临时排查材料",
          file_path: "/tmp/codeask/sess_e2e/启动排查记录.md",
          mime_type: "text/markdown",
          size_bytes: 2048,
          created_at: NOW,
          updated_at: NOW,
        },
      ]);
    }
    if (path === "/api/wiki/spaces/by-feature/7" && method === "GET") {
      return json(route, currentSpace);
    }
    if (path === "/api/wiki/tree?feature_id=7" && method === "GET") {
      return json(route, {
        space: currentSpace,
        nodes: buildTreeNodes(options.state),
      });
    }
    if (path === "/api/wiki/tree" && method === "GET") {
      return json(route, {
        space: currentSpace,
        nodes: buildTreeNodes(options.state),
      });
    }
    if (url.pathname === "/api/wiki/search" && method === "GET") {
      return json(route, { items: [] });
    }
    if (path === "/api/wiki/reports/projections?feature_id=7" && method === "GET") {
      return json(route, { items: [] });
    }
    if (path === "/api/wiki/documents/703" && method === "GET") {
      return json(route, {
        document_id: 9001,
        node_id: 703,
        title: options.state.documentTitle,
        current_version_id: 1,
        current_body_markdown: `# ${options.state.documentTitle}\n\n正文预览。`,
        draft_body_markdown: null,
        index_status: "ready",
        broken_refs_json: { links: [], assets: [] },
        resolved_refs_json: [],
        provenance_json: null,
        permissions: { read: true, write: true, admin: true },
      });
    }
    if (path === "/api/wiki/documents/703/versions" && method === "GET") {
      return json(route, {
        versions: [
          {
            id: 1,
            document_id: 9001,
            version_no: 1,
            body_markdown: `# ${options.state.documentTitle}\n\n正文预览。`,
            created_by_subject_id: "client_e2e",
            created_at: NOW,
            updated_at: NOW,
          },
        ],
      });
    }

    return json(route, {});
  });
}

function buildTreeNodes(state: {
  archivedVisible?: boolean;
  documentDeleted?: boolean;
  documentTitle: string;
}) {
  const nodes = [
    buildNode({
      id: -1,
      space_id: 0,
      feature_id: null,
      parent_id: null,
      type: "folder",
      name: "当前特性",
      path: "当前特性",
      system_role: "feature_group_current",
      sort_order: 0,
    }),
    buildNode({
      id: -2,
      space_id: 0,
      feature_id: null,
      parent_id: null,
      type: "folder",
      name: "历史特性",
      path: "历史特性",
      system_role: "feature_group_history",
      sort_order: 1,
    }),
    buildNode({
      id: -100007,
      space_id: 70,
      feature_id: 7,
      parent_id: -1,
      type: "folder",
      name: "支付结算",
      path: "当前特性/payment-settlement",
      system_role: "feature_space_current",
      sort_order: 0,
    }),
    buildNode({
      id: 701,
      space_id: 70,
      feature_id: 7,
      parent_id: -100007,
      type: "folder",
      name: "知识库",
      path: "knowledge-base",
      system_role: "knowledge_base",
      sort_order: 0,
    }),
    buildNode({
      id: 702,
      space_id: 70,
      feature_id: 7,
      parent_id: -100007,
      type: "folder",
      name: "问题定位报告",
      path: "reports",
      system_role: "reports",
      sort_order: 1,
    }),
  ];

  if (!state.documentDeleted) {
    nodes.push(buildDocumentNode(state.documentTitle));
  }

  if (state.archivedVisible !== false) {
    nodes.push(
      buildNode({
        id: -100008,
        space_id: 71,
        feature_id: 8,
        parent_id: -2,
        type: "folder",
        name: "历史支付",
        path: "历史特性/history-payment",
        system_role: "feature_space_history",
        sort_order: 0,
      }),
    );
  }

  return nodes;
}

function buildDocumentNode(name = "支付回调手册") {
  return buildNode({
    id: 703,
    space_id: 70,
    feature_id: 7,
    parent_id: 701,
    type: "document",
    name,
    path: "knowledge-base/payment-callback-runbook",
    system_role: null,
    sort_order: 0,
  });
}

function buildNode(
  overrides: Partial<{
    id: number;
    space_id: number;
    feature_id: number | null;
    parent_id: number | null;
    type: string;
    name: string;
    path: string;
    system_role: string | null;
    sort_order: number;
  }>,
) {
  return {
    id: 0,
    space_id: 0,
    feature_id: null,
    parent_id: null,
    type: "folder",
    name: "节点",
    path: "node",
    system_role: null,
    sort_order: 0,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function buildWikiSource(overrides: Partial<{
  id: number;
  kind: "directory_import" | "manual_upload" | "session_promotion";
  display_name: string;
  uri: string | null;
  metadata_json: Record<string, unknown> | null;
  status: "active" | "failed" | "archived";
  last_synced_at: string | null;
}>) {
  return {
    id: 801,
    space_id: 70,
    kind: "directory_import" as const,
    display_name: "来源",
    uri: null,
    metadata_json: null,
    status: "active" as const,
    last_synced_at: null,
    created_at: NOW,
    updated_at: NOW,
    ...overrides,
  };
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
