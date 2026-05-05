import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installMockUploadXhr() {
  const uploadRequests: Array<{
    emitProgress: (loaded: number, total: number) => void;
    respond: (body: unknown, status?: number) => void;
  }> = [];

  class MockUploadTarget {
    private progressListeners: Array<(event: ProgressEvent<EventTarget>) => void> = [];

    addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
      if (type !== "progress") {
        return;
      }
      this.progressListeners.push((event) => {
        if (typeof listener === "function") {
          listener(event);
          return;
        }
        listener.handleEvent(event);
      });
    }

    emitProgress(loaded: number, total: number) {
      const event = {
        lengthComputable: true,
        loaded,
        total,
      } as ProgressEvent<EventTarget>;
      this.progressListeners.forEach((listener) => listener(event));
    }
  }

  class MockXMLHttpRequest {
    upload = new MockUploadTarget();
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
      const uploadRequest = {
        emitProgress: (loaded: number, total: number) => {
          this.upload.emitProgress(loaded, total);
        },
        respond: (body: unknown, status = 200) => {
          this.status = status;
          this.responseText = JSON.stringify(body);
          this.listeners.load?.forEach((listener) => listener());
        },
      };
      uploadRequests.push(uploadRequest);
    }
  }

  vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest as unknown as typeof XMLHttpRequest);

  return {
    getUploadRequest: (index = 0) => uploadRequests[index],
    getUploadRequests: () => uploadRequests,
  };
}

describe("Wiki import workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("imports markdown from the wiki drawer and opens the imported document preview", async () => {
    let importApplied = false;
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
              ...(importApplied
                ? [
                    {
                      id: 705,
                      space_id: 70,
                      feature_id: 7,
                      parent_id: 701,
                      type: "document",
                      name: "Runbook",
                      path: "knowledge-base/runbook",
                      system_role: null,
                      sort_order: 0,
                      created_at: "2026-04-30T10:00:00",
                      updated_at: "2026-04-30T10:00:00",
                    },
                  ]
                : []),
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
                status: importApplied ? "uploaded" : "pending",
                progress_percent: importApplied ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_301/Runbook.md",
                result_node_id: importApplied ? 705 : null,
              },
            ],
          });
        }
        if (path === "/api/wiki/documents/705") {
          return jsonResponse({
            document_id: 1705,
            node_id: 705,
            title: "Runbook",
            current_version_id: 2705,
            current_body_markdown: "# Runbook\n\n这里是新导入的正文。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "directory_import" },
            permissions: { read: true, write: true, admin: false },
          });
        }
        if (path === "/api/wiki/documents/705/versions") {
          return jsonResponse({
            versions: [
              {
                id: 2705,
                document_id: 1705,
                version_no: 1,
                body_markdown: "# Runbook\n\n这里是新导入的正文。",
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

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    const markdownFile = new File(["# Runbook\n\n这里是新导入的正文。"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(markdownInput, {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(getUploadRequest()).toBeDefined();
    });

    await act(async () => {
      importApplied = true;
      getUploadRequest()?.respond({
        session: {
          id: 301,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "completed",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 1,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 1,
            conflict_count: 0,
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
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_301/Runbook.md",
          result_node_id: 705,
        },
      });
    });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expect(await screen.findByText("这里是新导入的正文。")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Runbook" })).toBeInTheDocument();
  });

  it("allows closing the import drawer after upload completion even while post-refresh is still running", async () => {
    let importApplied = false;
    let itemRequestCount = 0;
    let completedRefreshRequested = false;
    let resolveCompletedItems: (() => void) | null = null;
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
              ...(importApplied
                ? [
                    {
                      id: 705,
                      space_id: 70,
                      feature_id: 7,
                      parent_id: 701,
                      type: "document",
                      name: "Runbook",
                      path: "knowledge-base/runbook",
                      system_role: null,
                      sort_order: 0,
                      created_at: "2026-04-30T10:00:00",
                      updated_at: "2026-04-30T10:00:00",
                    },
                  ]
                : []),
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
              id: 303,
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
        if (path === "/api/wiki/import-sessions/303/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 303,
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
        if (path === "/api/wiki/import-sessions/303/items") {
          itemRequestCount += 1;
          if (importApplied && itemRequestCount >= 2) {
            completedRefreshRequested = true;
            return new Promise((resolve) => {
              resolveCompletedItems = () =>
                resolve(
                  jsonResponse({
                    items: [
                      {
                        id: 1,
                        source_path: "Runbook.md",
                        target_path: "knowledge-base/runbook",
                        item_kind: "document",
                        status: "uploaded",
                        progress_percent: 100,
                        ignore_reason: null,
                        staging_path: "/tmp/wiki/imports/session_303/Runbook.md",
                        result_node_id: 705,
                      },
                    ],
                  }),
                );
            });
          }
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook.md",
                target_path: "knowledge-base/runbook",
                item_kind: "document",
                status: importApplied ? "uploaded" : "pending",
                progress_percent: importApplied ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_303/Runbook.md",
                result_node_id: importApplied ? 705 : null,
              },
            ],
          });
        }
        if (path === "/api/wiki/documents/705") {
          return jsonResponse({
            document_id: 1705,
            node_id: 705,
            title: "Runbook",
            current_version_id: 2705,
            current_body_markdown: "# Runbook\n\n这里是新导入的正文。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "directory_import" },
            permissions: { read: true, write: true, admin: false },
          });
        }
        if (path === "/api/wiki/documents/705/versions") {
          return jsonResponse({
            versions: [
              {
                id: 2705,
                document_id: 1705,
                version_no: 1,
                body_markdown: "# Runbook\n\n这里是新导入的正文。",
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

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    const markdownFile = new File(["# Runbook\n\n这里是新导入的正文。"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(markdownInput, {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(getUploadRequest()).toBeDefined();
    });

    await act(async () => {
      importApplied = true;
      getUploadRequest()?.respond({
        session: {
          id: 303,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "completed",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 1,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 1,
            conflict_count: 0,
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
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_303/Runbook.md",
          result_node_id: 705,
        },
      });
    });

    await waitFor(() => {
      expect(completedRefreshRequested).toBe(true);
    });

    expect(screen.getByText("队列已处理完成")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));

    await waitFor(() => {
      expect(screen.queryByText("导入尚未完成")).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "导入 Wiki" })).not.toBeInTheDocument();
    });

    await act(async () => {
      resolveCompletedItems?.();
    });

    expect(await screen.findByText("这里是新导入的正文。")).toBeInTheDocument();
  });

  it("shows per-file upload progress while the import request is still in flight", async () => {
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
              id: 302,
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
        if (path === "/api/wiki/import-sessions/302/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 302,
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
        if (path === "/api/wiki/import-sessions/302/items") {
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook.md",
                target_path: "knowledge-base/runbook",
                item_kind: "document",
                status: "pending",
                progress_percent: 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_302/Runbook.md",
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

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    const markdownFile = new File(["# Runbook\n\n上传进度测试"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(markdownInput, {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(getUploadRequest()).toBeDefined();
    });

    await act(async () => {
      getUploadRequest()?.emitProgress(32, 64);
    });

    expect(await screen.findByText("上传中")).toBeInTheDocument();
    expect(await screen.findByText("总进度 50%")).toBeInTheDocument();
    expect(await screen.findByText("当前处理 Runbook.md")).toBeInTheDocument();

    await act(async () => {
      getUploadRequest()?.respond({
        session: {
          id: 302,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "completed",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 1,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 1,
            conflict_count: 0,
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
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_302/Runbook.md",
          result_node_id: 705,
        },
      });
    });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("avoids refetching the full import queue after every successful file upload", async () => {
    let itemsRequestCount = 0;
    const { getUploadRequests } = installMockUploadXhr();

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
              id: 350,
              space_id: 70,
              parent_id: 701,
              mode: "markdown",
              status: "running",
              requested_by_subject_id: "client_test",
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
        if (path === "/api/wiki/import-sessions/350/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 350,
            space_id: 70,
            parent_id: 701,
            mode: "markdown",
            status: "running",
            requested_by_subject_id: "client_test",
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
        if (path === "/api/wiki/import-sessions/350/items") {
          itemsRequestCount += 1;
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook-A.md",
                target_path: "knowledge-base/runbook-a",
                item_kind: "document",
                status: itemsRequestCount >= 2 ? "uploaded" : "pending",
                progress_percent: itemsRequestCount >= 2 ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_350/Runbook-A.md",
                result_node_id: null,
              },
              {
                id: 2,
                source_path: "Runbook-B.md",
                target_path: "knowledge-base/runbook-b",
                item_kind: "document",
                status: itemsRequestCount >= 2 ? "uploaded" : "pending",
                progress_percent: itemsRequestCount >= 2 ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_350/Runbook-B.md",
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

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    fireEvent.change(markdownInput, {
      target: {
        files: [
          new File(["# Runbook A"], "Runbook-A.md", { type: "text/markdown" }),
          new File(["# Runbook B"], "Runbook-B.md", { type: "text/markdown" }),
        ],
      },
    });

    await waitFor(() => {
      expect(getUploadRequests()).toHaveLength(1);
    });

    await act(async () => {
      getUploadRequests()[0]?.respond({
        session: {
          id: 350,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "running",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 2,
            pending_count: 1,
            uploading_count: 0,
            uploaded_count: 1,
            conflict_count: 0,
            failed_count: 0,
            ignored_count: 0,
            skipped_count: 0,
          },
        },
        item: {
          id: 1,
          source_path: "Runbook-A.md",
          target_path: "knowledge-base/runbook-a",
          item_kind: "document",
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_350/Runbook-A.md",
          result_node_id: null,
        },
      });
    });

    await waitFor(() => {
      expect(getUploadRequests()).toHaveLength(2);
    });

    await act(async () => {
      getUploadRequests()[1]?.respond({
        session: {
          id: 350,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "completed",
          requested_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
          summary: {
            total_files: 2,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 2,
            conflict_count: 0,
            failed_count: 0,
            ignored_count: 0,
            skipped_count: 0,
          },
        },
        item: {
          id: 2,
          source_path: "Runbook-B.md",
          target_path: "knowledge-base/runbook-b",
          item_kind: "document",
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_350/Runbook-B.md",
          result_node_id: null,
        },
      });
    });

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    expect(itemsRequestCount).toBe(2);
  });

  it("marks the queue item as failed when the upload request returns an error", async () => {
    let uploadFailed = false;
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
              id: 303,
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
        if (path === "/api/wiki/import-sessions/303/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 303,
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
        if (path === "/api/wiki/import-sessions/303/items") {
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook.md",
                target_path: "knowledge-base/runbook",
                item_kind: "document",
                status: uploadFailed ? "failed" : "pending",
                progress_percent: uploadFailed ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_303/Runbook.md",
                result_node_id: null,
              },
            ],
          });
        }
        if (path === "/api/wiki/import-sessions/303") {
          return jsonResponse({
            id: 303,
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
              conflict_count: 0,
              failed_count: 1,
              ignored_count: 0,
              skipped_count: 0,
            },
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    const markdownFile = new File(["# Runbook\n\n上传失败测试"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(markdownInput, {
      target: { files: [markdownFile] },
    });

    await waitFor(() => {
      expect(getUploadRequest()).toBeDefined();
    });

    await act(async () => {
      uploadFailed = true;
      getUploadRequest()?.respond({ detail: "upload failed" }, 500);
    });

    expect(await screen.findByText("upload failed")).toBeInTheDocument();
    expect(await screen.findByText("失败")).toBeInTheDocument();
  });

  it("continues uploading later files after one queue item fails", async () => {
    let firstFailed = false;
    let secondUploaded = false;
    const { getUploadRequest, getUploadRequests } = installMockUploadXhr();

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
              id: 304,
              space_id: 70,
              parent_id: 701,
              mode: "markdown",
              status: "running",
              requested_by_subject_id: "client_test",
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
        if (path === "/api/wiki/import-sessions/304/scan" && init?.method === "POST") {
          return jsonResponse({
            id: 304,
            space_id: 70,
            parent_id: 701,
            mode: "markdown",
            status: "running",
            requested_by_subject_id: "client_test",
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
        if (path === "/api/wiki/import-sessions/304/items") {
          return jsonResponse({
            items: [
              {
                id: 1,
                source_path: "Runbook-A.md",
                target_path: "knowledge-base/runbook-a",
                item_kind: "document",
                status: firstFailed ? "failed" : "pending",
                progress_percent: firstFailed ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_304/Runbook-A.md",
                result_node_id: null,
              },
              {
                id: 2,
                source_path: "Runbook-B.md",
                target_path: "knowledge-base/runbook-b",
                item_kind: "document",
                status: secondUploaded ? "uploaded" : "pending",
                progress_percent: secondUploaded ? 100 : 0,
                ignore_reason: null,
                staging_path: "/tmp/wiki/imports/session_304/Runbook-B.md",
                result_node_id: secondUploaded ? 706 : null,
              },
            ],
          });
        }
        if (path === "/api/wiki/import-sessions/304") {
          return jsonResponse({
            id: 304,
            space_id: 70,
            parent_id: 701,
            mode: "markdown",
            status: "running",
            requested_by_subject_id: "client_test",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
            summary: {
              total_files: 2,
              pending_count: secondUploaded ? 0 : 1,
              uploading_count: 0,
              uploaded_count: secondUploaded ? 1 : 0,
              conflict_count: 0,
              failed_count: 1,
              ignored_count: 0,
              skipped_count: 0,
            },
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const wikiTreePane = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.click(
      await within(wikiTreePane).findByRole("button", {
        name: "打开节点 知识库 的更多操作",
      }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "导入 Wiki" }));

    const dialog = await screen.findByRole("dialog");
    const markdownInput = within(dialog).getByLabelText("选择 Markdown 文件");
    const markdownFiles = [
      new File(["# Runbook A\n\n失败"], "Runbook-A.md", {
        type: "text/markdown",
      }),
      new File(["# Runbook B\n\n继续"], "Runbook-B.md", {
        type: "text/markdown",
      }),
    ];
    fireEvent.change(markdownInput, {
      target: { files: markdownFiles },
    });

    await waitFor(() => {
      expect(getUploadRequests()).toHaveLength(1);
    });

    await act(async () => {
      firstFailed = true;
      getUploadRequest(0)?.respond({ detail: "first upload failed" }, 500);
    });

    await waitFor(() => {
      expect(getUploadRequests()).toHaveLength(2);
    });

    await act(async () => {
      secondUploaded = true;
      getUploadRequest(1)?.respond({
        session: {
          id: 304,
          space_id: 70,
          parent_id: 701,
          mode: "markdown",
          status: "running",
          requested_by_subject_id: "client_test",
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
        },
        item: {
          id: 2,
          source_path: "Runbook-B.md",
          target_path: "knowledge-base/runbook-b",
          item_kind: "document",
          status: "uploaded",
          progress_percent: 100,
          ignore_reason: null,
          staging_path: "/tmp/wiki/imports/session_304/Runbook-B.md",
          result_node_id: 706,
        },
      });
    });

    expect(await screen.findByText("first upload failed")).toBeInTheDocument();
    expect(await screen.findByText("失败 1")).toBeInTheDocument();
    expect(await screen.findByText("已上传 1")).toBeInTheDocument();
  });
});
