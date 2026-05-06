import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki node ordering workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=704");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("falls back to legacy node updates when the move endpoint returns 405", async () => {
    let documents = [
      {
        id: 703,
        name: "Alpha",
        path: "knowledge-base/alpha",
        sort_order: 0,
      },
      {
        id: 704,
        name: "Beta",
        path: "knowledge-base/beta",
        sort_order: 1,
      },
    ];

    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            ...documents.map((document) => ({
              id: document.id,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: document.name,
              path: document.path,
              system_role: null,
              sort_order: document.sort_order,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            })),
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
      if (path === "/api/wiki/documents/704") {
        return jsonResponse({
          document_id: 1704,
          node_id: 704,
          title: "Beta",
          current_version_id: 2704,
          current_body_markdown: "# Beta\n\n正文。",
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/wiki/documents/704/versions") {
        return jsonResponse({
          versions: [
            {
              id: 2704,
              document_id: 1704,
              version_no: 1,
              body_markdown: "# Beta\n\n正文。",
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/nodes/704/move" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as {
          target_parent_id: number | null;
          target_index: number;
        };
        expect(payload).toEqual({ target_parent_id: 701, target_index: 0 });
        return jsonResponse({ detail: "Method Not Allowed" }, 405);
      }
      if (path === "/api/wiki/nodes/704" && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body)) as {
          parent_id?: number | null;
          sort_order?: number | null;
        };
        expect(payload).toEqual({ sort_order: 0 });
        documents = [
          { ...documents[1], sort_order: 0 },
          { ...documents[0], sort_order: 1 },
        ];
        return jsonResponse({
          id: 704,
          space_id: 70,
          feature_id: 7,
          parent_id: 701,
          type: "document",
          name: "Beta",
          path: "knowledge-base/beta",
          system_role: null,
          sort_order: 0,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (path === "/api/wiki/nodes/703" && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body)) as { sort_order?: number | null };
        expect(payload).toEqual({ sort_order: 1 });
        return jsonResponse({
          id: 703,
          space_id: 70,
          feature_id: 7,
          parent_id: 701,
          type: "document",
          name: "Alpha",
          path: "knowledge-base/alpha",
          system_role: null,
          sort_order: 1,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchSpy);

    render(<App />);

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });

    fireEvent.click(
      await within(treePane).findByRole("button", {
        name: /打开节点 Beta 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "上移" }));

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/wiki/nodes/704/move",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/wiki/nodes/704",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    await waitFor(() => {
      const orderedButtons = within(treePane)
        .getAllByRole("button")
        .filter((button) => button.className.includes("wiki-tree-button"))
        .map((button) => button.textContent ?? "")
        .filter((label) => label.includes("Alpha") || label.includes("Beta"));
      expect(orderedButtons.slice(0, 2)).toEqual(["Beta", "Alpha"]);
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Wiki 节点顺序已更新");
  });

  it("refetches the active document after moving it into another folder", async () => {
    let documentParentId = 701;
    let documentPath = "knowledge-base/xiaomi";
    let documentRequestCount = 0;

    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            name: "小米",
            slug: "xiaomi",
            description: "小米知识库",
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
              name: "小米",
              path: "当前特性/xiaomi",
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
              id: 705,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "folder",
              name: "test",
              path: "knowledge-base/test",
              system_role: null,
              sort_order: 0,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: 706,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "folder",
              name: "Untitled.assets",
              path: "knowledge-base/Untitled.assets",
              system_role: null,
              sort_order: 1,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: 704,
              space_id: 70,
              feature_id: 7,
              parent_id: documentParentId,
              type: "document",
              name: "Xiaomi",
              path: documentPath,
              system_role: null,
              sort_order: 2,
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
          display_name: "小米",
          slug: "xiaomi",
          status: "ready",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (path === "/api/wiki/reports/projections?feature_id=7") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/wiki/documents/704") {
        documentRequestCount += 1;
        const broken = documentParentId === 705;
        return jsonResponse({
          document_id: 1704,
          node_id: 704,
          title: "Xiaomi",
          current_version_id: 2704,
          current_body_markdown:
            '<img src="Untitled.assets/image.png" alt="image" style="zoom:50%;" />',
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json: broken
            ? {
                links: [],
                assets: [
                  {
                    target: "Untitled.assets/image.png",
                    kind: "image",
                    resolved_path: "knowledge-base/test/Untitled.assets/image.png",
                    resolved_node_id: null,
                    broken: true,
                  },
                ],
              }
            : { links: [], assets: [] },
          resolved_refs_json: [
            {
              target: "Untitled.assets/image.png",
              kind: "image",
              resolved_path: broken
                ? "knowledge-base/test/Untitled.assets/image.png"
                : "knowledge-base/Untitled.assets/image.png",
              resolved_node_id: broken ? null : 880,
              broken,
            },
          ],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/wiki/documents/704/versions") {
        return jsonResponse({
          versions: [
            {
              id: 2704,
              document_id: 1704,
              version_no: 1,
              body_markdown:
                '<img src="Untitled.assets/image.png" alt="image" style="zoom:50%;" />',
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/nodes/704/move" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as {
          target_parent_id: number | null;
          target_index: number;
        };
        expect(payload).toEqual({ target_parent_id: 705, target_index: 0 });
        documentParentId = 705;
        documentPath = "knowledge-base/test/xiaomi";
        return jsonResponse({
          id: 704,
          space_id: 70,
          feature_id: 7,
          parent_id: 705,
          type: "document",
          name: "Xiaomi",
          path: "knowledge-base/test/xiaomi",
          system_role: null,
          sort_order: 0,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchSpy);

    render(<App />);

    await waitFor(() => {
      expect(documentRequestCount).toBe(1);
    });

    fireEvent.dragStart(await screen.findByRole("button", { name: "Xiaomi" }));
    const insideDropZone = document.querySelector(
      '[data-drop-zone="inside"][data-node-id="705"]',
    ) as HTMLElement | null;
    expect(insideDropZone).not.toBeNull();
    fireEvent.dragOver(insideDropZone as HTMLElement);
    fireEvent.drop(insideDropZone as HTMLElement);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/wiki/nodes/704/move",
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => {
      expect(documentRequestCount).toBeGreaterThan(1);
    });
  });

  it("opens an error dialog when ordering fails", async () => {
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
              id: 703,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: "Alpha",
              path: "knowledge-base/alpha",
              system_role: null,
              sort_order: 0,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: 704,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: "Beta",
              path: "knowledge-base/beta",
              system_role: null,
              sort_order: 1,
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
      if (path === "/api/wiki/documents/704") {
        return jsonResponse({
          document_id: 1704,
          node_id: 704,
          title: "Beta",
          current_version_id: 2704,
          current_body_markdown: "# Beta\n\n正文。",
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/wiki/documents/704/versions") {
        return jsonResponse({
          versions: [
            {
              id: 2704,
              document_id: 1704,
              version_no: 1,
              body_markdown: "# Beta\n\n正文。",
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/nodes/704/move" && init?.method === "POST") {
        return jsonResponse({ detail: "Method Not Allowed" }, 405);
      }
      if (path === "/api/wiki/nodes/704" && init?.method === "PUT") {
        return jsonResponse({ detail: "legacy reorder blocked" }, 409);
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchSpy);

    render(<App />);

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });
    fireEvent.click(
      await within(treePane).findByRole("button", {
        name: /打开节点 Beta 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "上移" }));

    const dialog = await screen.findByRole("dialog", { name: "操作失败" });
    expect(dialog).toHaveTextContent("排序失败");
    expect(dialog).toHaveTextContent("legacy reorder blocked");
  });
});
