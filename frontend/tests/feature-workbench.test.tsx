import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_test",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

const existingRepo = {
  id: "repo_existing",
  name: "platform-api",
  source: "local_dir",
  url: null,
  local_path: "/repo/platform-api",
  bare_path: "/tmp/repos/repo_existing/bare",
  status: "ready",
  error_message: null,
  last_synced_at: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const defaultReports = [
  {
    id: 21,
    feature_id: 7,
    title: "启动失败复盘",
    body_markdown: "配置缺失导致启动失败",
    metadata_json: {},
    status: "draft",
    verified: false,
    verified_by: null,
    verified_at: null,
    created_by_subject_id: "client_test",
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
  },
];

function installFeatureFetchMock(
  options: {
    auth?: {
      subject_id: string;
      display_name: string;
      role: string;
      authenticated: boolean;
    };
    document?: {
      current_body_markdown: string;
      resolved_refs_json: unknown[];
      broken_refs_json?: {
        links: unknown[];
        assets: unknown[];
      };
    };
    repos?: unknown[];
    reports?: unknown[];
    featureWikiNodes?: unknown[];
  } = {},
) {
  const reportRows = new Map<number, Record<string, unknown>>(
    (options.reports ?? defaultReports).map((report) => {
      const row = report as Record<string, unknown>;
      return [Number(row.id), { ...row }];
    }),
  );
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/auth/me") {
        return jsonResponse(
          options.auth ?? {
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          },
        );
      }
      if (path === "/api/features" && init?.method !== "POST") {
        return jsonResponse([feature]);
      }
      if (path === "/api/features" && init?.method === "POST") {
        return jsonResponse(
          { ...feature, id: 8, name: "风控策略", slug: "risk-policy" },
          201,
        );
      }
      if (path === "/api/features/7" && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      if (path === "/api/documents?feature_id=7") {
        return jsonResponse([]);
      }
      if (path === "/api/wiki/tree?feature_id=7") {
        return jsonResponse({
          space: {
            id: 70,
            feature_id: 7,
            scope: "current",
            display_name: "支付结算",
            slug: "payment-settlement",
            status: "ready",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          nodes:
            options.featureWikiNodes ??
            [
              {
                id: 701,
                space_id: 70,
                parent_id: null,
                type: "folder",
                name: "知识库",
                path: "知识库",
                system_role: "knowledge_base",
                sort_order: 0,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 702,
                space_id: 70,
                parent_id: null,
                type: "folder",
                name: "问题定位报告",
                path: "问题定位报告",
                system_role: "reports",
                sort_order: 1,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 703,
                space_id: 70,
                parent_id: 701,
                type: "document",
                name: "支付接入说明",
                path: "知识库/支付接入说明",
                system_role: null,
                sort_order: 0,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
        });
      }
      if (path === "/api/wiki/tree") {
        return jsonResponse({
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
            {
              id: 702,
              space_id: 70,
              feature_id: 7,
              parent_id: -100007,
              type: "folder",
              name: "问题定位报告",
              path: "reports",
              system_role: "reports",
              sort_order: 200,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: 703,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: "支付接入说明",
              path: "knowledge-base/payment-access",
              system_role: null,
              sort_order: 0,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/reports/projections?feature_id=7") {
        return jsonResponse({
          items: [
            {
              node_id: 704,
              report_id: 21,
              feature_id: 7,
              title: "启动失败复盘",
              status: "draft",
              status_group: "draft",
              verified: false,
              verified_by: null,
              verified_at: null,
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/documents/703") {
        return jsonResponse({
          document_id: 1703,
          node_id: 703,
          title: "支付接入说明",
          current_version_id: 2703,
          current_body_markdown:
            options.document?.current_body_markdown ??
            "# 支付接入说明\n\n这里是接入说明正文。",
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json:
            options.document?.broken_refs_json ?? { links: [], assets: [] },
          resolved_refs_json: options.document?.resolved_refs_json ?? [],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/wiki/documents/703/versions") {
        return jsonResponse({
          versions: [
            {
              id: 2703,
              document_id: 1703,
              version_no: 1,
              body_markdown: "# 支付接入说明\n\n这里是接入说明正文。",
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/reports/by-node/704") {
        return jsonResponse({
          node_id: 704,
          report_id: 21,
          feature_id: 7,
          title: "启动失败复盘",
          body_markdown: "配置缺失导致启动失败",
          metadata_json: {},
          status: "draft",
          verified: false,
          verified_by: null,
          verified_at: null,
          created_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (path === "/api/documents" && init?.method === "POST") {
        return jsonResponse(
          {
            id: 12,
            feature_id: 7,
            kind: "markdown",
            title: "支付 Wiki",
            path: "payment.md",
            tags_json: null,
            summary: null,
            is_deleted: false,
            uploaded_by_subject_id: "client_test",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
          201,
        );
      }
      if (path === "/api/reports?feature_id=7") {
        return jsonResponse(Array.from(reportRows.values()));
      }
      const reportMatch = path.match(
        /^\/api\/reports\/(\d+)(?:\/(verify|reject|unverify))?$/,
      );
      if (reportMatch) {
        const reportId = Number(reportMatch[1]);
        const action = reportMatch[2];
        const report = reportRows.get(reportId);
        if (!report) {
          return jsonResponse({ detail: "report not found" }, 404);
        }
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          const updated = {
            ...report,
            ...("title" in body ? { title: body.title } : {}),
            ...("body_markdown" in body
              ? { body_markdown: body.body_markdown }
              : {}),
            ...("metadata" in body ? { metadata_json: body.metadata } : {}),
            updated_at: "2026-04-30T12:00:00",
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "DELETE") {
          reportRows.delete(reportId);
          return new Response(null, { status: 204 });
        }
        if (init?.method === "POST" && action === "verify") {
          const updated = {
            ...report,
            status: "verified",
            verified: true,
            verified_by: "client_test",
            verified_at: "2026-04-30T12:00:00",
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "POST" && action === "reject") {
          const updated = {
            ...report,
            status: "rejected",
            verified: false,
            verified_by: null,
            verified_at: null,
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "POST" && action === "unverify") {
          const updated = {
            ...report,
            status: "draft",
            verified: false,
            verified_by: null,
            verified_at: null,
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
      }
      if (path === "/api/repos") {
        if (init?.method === "POST") {
          return jsonResponse(
            {
              id: "repo_1",
              name: "codeask",
              source: "local_dir",
              url: null,
              local_path: "/repo/codeask",
              bare_path: "/tmp/repos/repo_1/bare",
              status: "registered",
              error_message: null,
              last_synced_at: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        return jsonResponse({ repos: options.repos ?? [] });
      }
      if (path === "/api/features/7/repos") {
        return jsonResponse({ repos: [] });
      }
      if (
        path === "/api/features/7/repos/repo_existing" &&
        init?.method === "POST"
      ) {
        return jsonResponse(existingRepo);
      }
      if (path === "/api/features/7/repos/repo_1" && init?.method === "POST") {
        return jsonResponse({
          id: "repo_1",
          name: "codeask",
          source: "local_dir",
          url: null,
          local_path: "/repo/codeask",
          bare_path: "/tmp/repos/repo_1/bare",
          status: "registered",
          error_message: null,
          last_synced_at: null,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (
        path === "/api/features/7/repos/repo_existing" &&
        init?.method === "DELETE"
      ) {
        return new Response(null, { status: 204 });
      }
      if (path === "/api/skills") {
        if (init?.method === "POST") {
          return jsonResponse(
            {
              id: "sk_1",
              name: "支付排障",
              scope: "feature",
              feature_id: 7,
              stage: "code_investigation",
              enabled: true,
              priority: 10,
              prompt_template: "按支付链路排查",
            },
            201,
          );
        }
        return jsonResponse([]);
      }
      throw new Error(`unexpected request ${path}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("FeatureWorkbench management actions", () => {
  it("shows a visible error when loading features fails instead of pretending the list is empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/features" && init?.method !== "POST") {
          return jsonResponse({ detail: "backend unavailable" }, 500);
        }
        throw new Error(`unexpected request ${path}`);
      }),
    );

    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));

    await waitFor(
      () => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "加载特性失败：backend unavailable",
        );
      },
      { timeout: 3000 },
    );
    expect(screen.queryByText("暂无特性")).not.toBeInTheDocument();
  });

  it("creates features from an inline list form", async () => {
    const fetchMock = installFeatureFetchMock();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "添加特性" }));
    fireEvent.change(screen.getByLabelText("特性名称"), {
      target: { value: "风控策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建特性" }));

    expect(await screen.findAllByText("风控策略")).not.toHaveLength(0);
    const [, init] = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/features" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      name: "风控策略",
    });
    expect(JSON.parse(String(init.body))).not.toHaveProperty("slug");
  });

  it("shows feature descriptions in the tree and hides slug badges from the detail header", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));

    const list = screen.getByRole("region", { name: "特性列表" });
    expect(await within(list).findByText("支付链路知识域")).toBeInTheDocument();
    expect(within(list).queryByText("payment-settlement")).not.toBeInTheDocument();

    expect(screen.getByText("支付链路知识域", { selector: ".page-header p" })).toBeInTheDocument();
    expect(screen.queryByText("payment-settlement")).not.toBeInTheDocument();
  });

  it("truncates long feature descriptions in the tree to a single ellipsis line", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));

    const list = screen.getByRole("region", { name: "特性列表" });
    const description = await within(list).findByText("支付链路知识域", {
      selector: ".feature-item-description",
    });
    expect(description).toHaveClass("feature-item-description");

    const styles = getComputedStyle(description);
    expect(styles.whiteSpace).toBe("nowrap");
    expect(styles.overflow).toBe("hidden");
    expect(styles.textOverflow).toBe("ellipsis");
  });

  it("shows wiki management, generated reports, links a repo, and creates a feature analysis policy in feature tabs", async () => {
    const fetchMock = installFeatureFetchMock({ repos: [existingRepo] });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));
    expect(
      await screen.findByRole("button", { name: "进入 Wiki 工作台" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("支付接入说明")).toBeInTheDocument();
    expect(await screen.findByText("这里是接入说明正文。")).toBeInTheDocument();
    expect(screen.queryByText(/篇报告$/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("支付接入说明", { selector: ".knowledge-preview-title" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "进入 Wiki 工作台" }));
    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    expect(within(wikiTreePane).getByLabelText("搜索 Wiki 目录")).toBeInTheDocument();
    expect(await within(wikiTreePane).findByRole("button", { name: "当前特性" })).toBeInTheDocument();
    expect(within(wikiTreePane).getByRole("button", { name: "历史特性" })).toBeInTheDocument();
    expect(within(wikiTreePane).getByRole("button", { name: "支付结算" })).toBeInTheDocument();
    expect(await screen.findByText("这里是接入说明正文。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findByRole("tab", { name: "问题报告" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    expect(await screen.findByText("启动失败复盘")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /启动失败复盘/ }));
    expect(screen.getByText("配置缺失导致启动失败")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "关联仓库" }));
    fireEvent.click(await screen.findByRole("checkbox"));

    fireEvent.click(screen.getByRole("tab", { name: "特性分析策略" }));
    fireEvent.click(screen.getByRole("button", { name: "添加分析策略" }));
    fireEvent.change(screen.getByLabelText("策略名称"), {
      target: { value: "支付排障" },
    });
    fireEvent.change(screen.getByLabelText("适用阶段"), {
      target: { value: "code_investigation" },
    });
    fireEvent.change(screen.getByLabelText("优先级"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Prompt 内容"), {
      target: { value: "按支付链路排查" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建分析策略" }));
    expect(await screen.findByText("支付排障")).toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/features/7/repos/repo_existing",
      expect.objectContaining({ method: "POST" }),
    );
    const policyCreate = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/skills" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(policyCreate[1].body))).toMatchObject({
      name: "支付排障",
      scope: "feature",
      feature_id: 7,
      stage: "code_investigation",
      enabled: true,
      priority: 10,
      prompt_template: "按支付链路排查",
    });

    expect(
      within(screen.getByRole("region", { name: "特性列表" })).queryByText(
        "Wiki",
      ),
    ).not.toBeInTheDocument();
  });

  it("resolves relative wiki links and images inside the feature knowledge preview", async () => {
    installFeatureFetchMock({
      document: {
        current_body_markdown:
          "# 支付接入说明\n\n[排障手册](./runbook.md)\n\n![架构图](./images/diagram.png)",
        resolved_refs_json: [
          {
            target: "./runbook.md",
            kind: "link",
            resolved_path: "知识库/runbook.md",
            resolved_node_id: 709,
            broken: false,
          },
          {
            target: "./images/diagram.png",
            kind: "image",
            resolved_path: "知识库/images/diagram.png",
            resolved_node_id: 811,
            broken: false,
          },
        ],
      },
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));

    expect(await screen.findByRole("link", { name: "排障手册" })).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=709",
    );
    expect(await screen.findByRole("img", { name: "架构图" })).toHaveAttribute(
      "src",
      "/api/wiki/assets/811/content",
    );
  });

  it("keeps only the knowledge root expanded by default in the feature knowledge tree", async () => {
    installFeatureFetchMock({
      featureWikiNodes: [
        {
          id: 701,
          space_id: 70,
          parent_id: null,
          type: "folder",
          name: "知识库",
          path: "知识库",
          system_role: "knowledge_base",
          sort_order: 0,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
        {
          id: 710,
          space_id: 70,
          parent_id: 701,
          type: "folder",
          name: "接入指南",
          path: "知识库/接入指南",
          system_role: null,
          sort_order: 0,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
        {
          id: 711,
          space_id: 70,
          parent_id: 710,
          type: "document",
          name: "支付接入说明",
          path: "知识库/接入指南/支付接入说明",
          system_role: null,
          sort_order: 0,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
        {
          id: 702,
          space_id: 70,
          parent_id: null,
          type: "folder",
          name: "问题定位报告",
          path: "问题定位报告",
          system_role: "reports",
          sort_order: 1,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        },
      ],
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));

    const knowledgeRoot = await screen.findByRole("button", { name: "知识库" });
    expect(knowledgeRoot).toHaveAttribute("aria-expanded", "true");

    const guideFolder = await screen.findByRole("button", { name: "接入指南" });
    expect(guideFolder).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "支付接入说明" })).not.toBeInTheDocument();

    fireEvent.click(guideFolder);
    expect(await screen.findByRole("button", { name: "支付接入说明" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "接入指南" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "接入指南" }));
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "支付接入说明" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "接入指南" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("keeps wiki management actions visible for authenticated non-owner members in v1.0.1", async () => {
    installFeatureFetchMock({
      auth: {
        subject_id: "viewer_test",
        display_name: "viewer_test",
        role: "member",
        authenticated: true,
      },
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));
    fireEvent.click(await screen.findByRole("button", { name: "进入 Wiki 工作台" }));

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });

    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: /打开节点 知识库 的更多操作/,
      }),
    );
    expect(screen.getByRole("menuitem", { name: "新建目录" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "新建 Wiki" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "导入 Wiki" })).toBeInTheDocument();

    expect(await screen.findByRole("button", { name: "编辑" })).toBeInTheDocument();
  });

  it("shows report status filters and filters reports by lifecycle state", async () => {
    installFeatureFetchMock({
      reports: [
        defaultReports[0],
        {
          ...defaultReports[0],
          id: 22,
          title: "验证通过复盘",
          body_markdown: "人工验证后的报告",
          status: "verified",
          verified: true,
          verified_by: "maintainer",
          verified_at: "2026-04-30T11:00:00",
        },
      ],
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));

    const statusTabs = await screen.findByRole("tablist", {
      name: "报告状态筛选",
    });
    expect(within(statusTabs).getByRole("tab", { name: /全部/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /草稿/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /已验证/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /未通过/ })).toBeInTheDocument();

    fireEvent.click(within(statusTabs).getByRole("tab", { name: /已验证/ }));

    expect(await screen.findByText("验证通过复盘")).toBeInTheDocument();
    expect(screen.queryByText("启动失败复盘")).not.toBeInTheDocument();
  });

  it("constrains rendered markdown report details inside the preview pane", async () => {
    installFeatureFetchMock({
      reports: [
        {
          ...defaultReports[0],
          id: 23,
          title: "长格式报告",
          body_markdown:
            "| 字段 | 值 |\n| --- | --- |\n| 路径 | `/var/log/codeask/service/node-a/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.log` |\n\n`trace_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`",
        },
      ],
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    fireEvent.click(await screen.findByRole("button", { name: /长格式报告/ }));

    const previewTitle = screen.getByText("长格式报告", {
      selector: ".report-preview-title",
    });
    const preview = previewTitle.closest(".report-preview");
    expect(preview).toBeInTheDocument();
    expect(["0", "0px"]).toContain(
      getComputedStyle(preview as Element).minWidth,
    );
    expect(getComputedStyle(preview as Element).overflowY).toBe("auto");
    expect(getComputedStyle(screen.getByRole("table")).overflowX).toBe("auto");
  });

  it("edits, verifies, rejects, un-verifies, and deletes reports from the detail pane", async () => {
    const fetchMock = installFeatureFetchMock({
      reports: [
        {
          ...defaultReports[0],
          body_markdown: "初始报告内容",
        },
      ],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    fireEvent.click(await screen.findByRole("button", { name: /启动失败复盘/ }));

    expect(screen.getByRole("button", { name: "编辑报告" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除报告" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "验证通过" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "验证不通过" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.change(screen.getByLabelText("报告标题"), {
      target: { value: "编辑后的复盘" },
    });
    fireEvent.change(screen.getByLabelText("报告内容"), {
      target: { value: "编辑后的报告正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存报告" }));
    expect(await screen.findAllByText("编辑后的复盘")).not.toHaveLength(0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21",
      expect.objectContaining({ method: "PUT" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "验证通过" }));
    expect(await screen.findByText("已验证")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/verify",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "撤销验证" }));
    expect(await screen.findByText("草稿")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/unverify",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "验证不通过" }));
    expect(await screen.findByText("未通过")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/reject",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "删除报告" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/reports/21",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(screen.queryByText("编辑后的复盘")).not.toBeInTheDocument();
  });

  it("links existing global repos inside the selected feature page", async () => {
    const fetchMock = installFeatureFetchMock({ repos: [existingRepo] });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "关联仓库" }));

    expect(await screen.findAllByText(/platform-api/)).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7/repos/repo_existing",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("deletes a feature from the feature list after confirmation", async () => {
    const fetchMock = installFeatureFetchMock();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "删除特性 支付结算" }));
    expect(
      screen.getByRole("dialog", { name: "删除特性" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    await waitFor(() => {
      expect(
        within(screen.getByRole("region", { name: "特性列表" })).queryByText(
          "支付结算",
        ),
      ).not.toBeInTheDocument();
    });
  });
});
