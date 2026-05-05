import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installMockUploadXhr() {
  let uploadRequest:
    | {
        respond: (body: unknown, status?: number) => void;
      }
    | undefined;

  class MockXMLHttpRequest {
    upload = {
      addEventListener() {},
    };
    readyState = 4;
    status = 0;
    responseText = "";
    withCredentials = false;
    private headers = new Map<string, string>();
    private listeners: Record<string, Array<() => void>> = {};

    open() {}

    setRequestHeader(name: string, value: string) {
      this.headers.set(name, value);
    }

    addEventListener(type: string, listener: () => void) {
      this.listeners[type] ??= [];
      this.listeners[type].push(listener);
    }

    getResponseHeader(name: string) {
      if (name.toLowerCase() === "content-type") {
        return "application/json";
      }
      return this.headers.get(name) ?? null;
    }

    send() {
      uploadRequest = {
        respond: (body: unknown, status = 200) => {
          this.status = status;
          this.responseText = JSON.stringify(body);
          this.listeners.load?.forEach((listener) => listener());
        },
      };
    }
  }

  vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest as unknown as typeof XMLHttpRequest);
  return {
    getUploadRequest: () => uploadRequest,
  };
}

describe("CodeAsk AppShell information architecture", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("keeps the primary navigation to sessions, features, wiki, and settings", () => {
    render(<App />);

    const navigation = screen.getByRole("navigation", { name: "主导航" });
    expect(
      within(navigation).getByRole("button", { name: "会话" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "特性" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "设置" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "Wiki" }),
    ).toBeInTheDocument();
    expect(within(navigation).queryByText("全局配置")).not.toBeInTheDocument();
  });

  it("allows primary and secondary sidebars to collapse and expand", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "收起主导航" }));
    expect(
      screen.getByRole("button", { name: "展开主导航" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "收起会话列表" }));
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开会话列表" }));
    expect(screen.getByPlaceholderText("搜索会话")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    fireEvent.click(screen.getByRole("button", { name: "收起特性列表" }));
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开特性列表" }));
    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    fireEvent.click(screen.getByRole("button", { name: "收起设置导航" }));
    expect(
      screen.queryByRole("button", { name: "用户设置" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开设置导航" }));
    expect(
      await screen.findByRole("button", { name: "用户设置" }),
    ).toBeInTheDocument();
  });

  it("shows the session workspace as a three-column page with search, create, and progress", () => {
    render(<App />);

    expect(screen.getByPlaceholderText("搜索会话")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新建会话" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("我的会话")).not.toBeInTheDocument();
    expect(screen.queryByText("全部会话")).not.toBeInTheDocument();

    expect(
      screen.getByRole("region", { name: "会话列表" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "会话消息" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "调查进度" }),
    ).toBeInTheDocument();
  });

  it("opens the feature workbench with list search, create, and same-page detail tabs", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));

    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "添加特性" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "设置" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "知识库" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "问题报告" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "关联仓库" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "特性分析策略" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/features");
  });

  it("restores the active primary section from the URL hash after reload", async () => {
    window.history.replaceState(null, "", "/#/settings");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "用户配置" }),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "设置" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("restores the feature workbench from the URL hash after reload", () => {
    window.history.replaceState(null, "", "/#/features");

    render(<App />);

    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "特性" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("restores the wiki workbench with current and historical feature roots instead of a feature selector", async () => {
    window.history.replaceState(null, "", "/#/wiki");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (path === "/api/features") {
          return jsonResponse([
            {
              id: 7,
              name: "支付结算",
              slug: "payment-settlement",
              description: "支付链路知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
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
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/documents/703") {
          return jsonResponse({
            document_id: 1703,
            node_id: 703,
            title: "支付接入说明",
            current_version_id: 2703,
            current_body_markdown: "# 支付接入说明\n\n这里是独立 Wiki 预览正文。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
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
                body_markdown: "# 支付接入说明\n\n这里是独立 Wiki 预览正文。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const tree = await screen.findByRole("complementary", { name: "Wiki 目录树" });
    expect(await within(tree).findByRole("button", { name: "当前特性" })).toBeInTheDocument();
    expect(await within(tree).findByRole("button", { name: "历史特性" })).toBeInTheDocument();
    expect(await within(tree).findByRole("button", { name: "支付结算" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(await screen.findByText("这里是独立 Wiki 预览正文。")).toBeInTheDocument();
  });

  it("keeps an archived feature wiki route readable even when the active feature list no longer contains it", async () => {
    window.history.replaceState(null, "", "/#/wiki?feature=42&node=4203");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (path === "/api/features") {
          return jsonResponse([
            {
              id: 7,
              name: "支付结算",
              slug: "payment-settlement",
              description: "支付链路知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
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
                id: -200042,
                space_id: 420,
                feature_id: 42,
                parent_id: -2,
                type: "folder",
                name: "Legacy Billing",
                path: "历史特性/legacy-billing",
                system_role: "feature_space_history",
                sort_order: 0,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 4201,
                space_id: 420,
                feature_id: 42,
                parent_id: -200042,
                type: "folder",
                name: "知识库",
                path: "knowledge-base",
                system_role: "knowledge_base",
                sort_order: 100,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 4203,
                space_id: 420,
                feature_id: 42,
                parent_id: 4201,
                type: "document",
                name: "Archived Runbook",
                path: "knowledge-base/archived-runbook",
                system_role: null,
                sort_order: 0,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/spaces/by-feature/42") {
          return jsonResponse({
            id: 420,
            feature_id: 42,
            scope: "history",
            display_name: "Legacy Billing",
            slug: "legacy-billing",
            status: "archived",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          });
        }
        if (path === "/api/wiki/reports/projections?feature_id=42") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/documents/4203") {
          return jsonResponse({
            document_id: 14203,
            node_id: 4203,
            title: "Archived Runbook",
            current_version_id: 24203,
            current_body_markdown: "# Archived Runbook\n\n历史特性文档仍然可读。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "manual_create" },
            permissions: { read: true, write: true, admin: false },
          });
        }
        if (path === "/api/wiki/documents/4203/versions") {
          return jsonResponse({
            versions: [
              {
                id: 24203,
                document_id: 14203,
                version_no: 1,
                body_markdown: "# Archived Runbook\n\n历史特性文档仍然可读。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    expect(await screen.findByText("历史特性文档仍然可读。")).toBeInTheDocument();
    expect(window.location.hash).toBe("#/wiki?feature=42&node=4203");
    expect(screen.getByRole("button", { name: "Wiki" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("prompts before leaving wiki when an import drawer still has an unfinished session", async () => {
    window.history.replaceState(null, "", "/#/wiki");
    let uploadState: "pending" | "conflict" = "pending";
    const { getUploadRequest } = installMockUploadXhr();
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
        if (path === "/api/features") {
          return jsonResponse([
            {
              id: 7,
              name: "支付结算",
              slug: "payment-settlement",
              description: "支付链路知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
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
        if (path === "/api/wiki/spaces/by-feature/7") {
          return jsonResponse({
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
        if (path === "/api/wiki/reports/projections?feature_id=7") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/import-sessions" && init?.method === "POST") {
          return jsonResponse(
            {
              id: 301,
              space_id: 70,
              parent_id: 701,
              mode: "markdown",
              status: "running",
              requested_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
              summary: {
                total_files: 1,
                pending_count: 1,
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
        if (path === "/api/wiki/import-sessions/301/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 301,
            space_id: 70,
            parent_id: 701,
            mode: "markdown",
            status: "running",
            requested_by_subject_id: "client_test",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
            summary: {
              total_files: 1,
              pending_count: 1,
              uploading_count: 0,
              uploaded_count: 0,
              conflict_count: 0,
              failed_count: 0,
              ignored_count: 0,
              skipped_count: 0,
            },
          });
        }
        if (path === "/api/wiki/import-sessions/301/items") {
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook.md",
                target_path: "knowledge-base/runbook",
                item_kind: "document",
                status: uploadState === "pending" ? "pending" : "conflict",
                progress_percent: uploadState === "pending" ? 0 : 100,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_301/Runbook.md",
                result_node_id: null,
              },
            ],
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "导入 Wiki" }));

    const markdownFile = new File(["# Runbook"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(screen.getByLabelText("选择 Markdown 文件"), {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(getUploadRequest()).toBeDefined();
    });

    await act(async () => {
      uploadState = "conflict";
      getUploadRequest()?.respond({
        session: {
          id: 301,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "running",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 1,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 0,
            conflict_count: 1,
            failed_count: 0,
            ignored_count: 0,
            skipped_count: 0,
          },
        },
        item: {
          id: 1,
          source_path: "Runbook.md",
          target_path: "knowledge-base/runbook",
          item_kind: "document",
          status: "conflict",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_301/Runbook.md",
          result_node_id: null,
        },
      });
    });

    expect(await screen.findByText("冲突 1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "会话" }));
    expect(await screen.findByText("离开当前页面前，需要先决定是继续后台上传，还是直接取消本次导入。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "继续后台" }));
    expect(await screen.findByPlaceholderText("搜索会话")).toBeInTheDocument();
  });

  it("switches preview content when selecting another feature from the global wiki tree", async () => {
    window.history.replaceState(null, "", "/#/wiki");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (path === "/api/features") {
          return jsonResponse([
            {
              id: 7,
              name: "支付结算",
              slug: "payment-settlement",
              description: "支付链路知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: 8,
              name: "风控中心",
              slug: "risk-center",
              description: "风控规则与审计知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
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
              {
                id: -100008,
                space_id: 80,
                feature_id: 8,
                parent_id: -1,
                type: "folder",
                name: "风控中心",
                path: "当前特性/risk-center",
                system_role: "feature_space_current",
                sort_order: 1,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 801,
                space_id: 80,
                feature_id: 8,
                parent_id: -100008,
                type: "folder",
                name: "知识库",
                path: "knowledge-base",
                system_role: "knowledge_base",
                sort_order: 100,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
              {
                id: 803,
                space_id: 80,
                feature_id: 8,
                parent_id: 801,
                type: "document",
                name: "风控规则说明",
                path: "knowledge-base/risk-rules",
                system_role: null,
                sort_order: 0,
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/reports/projections?feature_id=7") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/reports/projections?feature_id=8") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/documents/703") {
          return jsonResponse({
            document_id: 1703,
            node_id: 703,
            title: "支付接入说明",
            current_version_id: 2703,
            current_body_markdown: "# 支付接入说明\n\n这里是支付知识。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
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
                body_markdown: "# 支付接入说明\n\n这里是支付知识。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/documents/803") {
          return jsonResponse({
            document_id: 1803,
            node_id: 803,
            title: "风控规则说明",
            current_version_id: 2803,
            current_body_markdown: "# 风控规则说明\n\n这里是风控知识。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "manual_create" },
            permissions: { read: true, write: true, admin: false },
          });
        }
        if (path === "/api/wiki/documents/803/versions") {
          return jsonResponse({
            versions: [
              {
                id: 2803,
                document_id: 1803,
                version_no: 1,
                body_markdown: "# 风控规则说明\n\n这里是风控知识。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    expect(await screen.findByText("这里是支付知识。")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "风控中心" }));
    expect(await screen.findByText("这里是风控知识。")).toBeInTheDocument();
  });

  it("renders report projection groups and opens report markdown from the global wiki tree", async () => {
    window.history.replaceState(null, "", "/#/wiki");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
        if (path === "/api/features") {
          return jsonResponse([
            {
              id: 7,
              name: "支付结算",
              slug: "payment-settlement",
              description: "支付链路知识域",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
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
            ],
          });
        }
        if (path === "/api/wiki/spaces/by-feature/7") {
          return jsonResponse({
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
        if (path === "/api/wiki/reports/projections?feature_id=7") {
          return jsonResponse({
            items: [
              {
                node_id: 704,
                report_id: 21,
                feature_id: 7,
                title: "支付超时复盘",
                status: "verified",
                status_group: "verified",
                verified: true,
                verified_by: "owner@test",
                verified_at: "2026-04-30T10:00:00",
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
            title: "支付超时复盘",
            body_markdown: "# 支付超时复盘\n\n这里是报告正文。",
            metadata_json: {},
            status: "verified",
            verified: true,
            verified_by: "owner@test",
            verified_at: "2026-04-30T10:00:00",
            created_by_subject_id: "owner@test",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const tree = await screen.findByRole("complementary", { name: "Wiki 目录树" });
    expect(await within(tree).findByRole("button", { name: "问题定位报告" })).toBeInTheDocument();
    fireEvent.click(within(tree).getByRole("button", { name: "问题定位报告" }));
    expect(await within(tree).findByRole("button", { name: "已验证" })).toBeInTheDocument();
    fireEvent.click(within(tree).getByRole("button", { name: "已验证" }));
    fireEvent.click(await within(tree).findByRole("button", { name: "支付超时复盘" }));

    expect(await screen.findByText("这里是报告正文。")).toBeInTheDocument();
    expect(screen.getAllByText("已验证").length).toBeGreaterThan(0);
  });

  it("keeps user settings under settings and hides global configuration for members", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(
      await screen.findByRole("heading", { name: "用户配置" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "全局配置" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "全局配置" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
  });
});
