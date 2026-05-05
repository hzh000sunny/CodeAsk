import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki tree resize workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("resizes the tree pane by dragging the separator between tree and content", async () => {
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
        if (path === "/api/wiki/documents/703") {
          return jsonResponse({
            document_id: 1703,
            node_id: 703,
            title: "支付接入说明",
            current_version_id: 2703,
            current_body_markdown: "# 支付接入说明\n\n正文。",
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
                body_markdown: "# 支付接入说明\n\n正文。",
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

    const workspace = await waitFor(() =>
      document.querySelector(".wiki-workspace") as HTMLElement | null,
    );
    expect(workspace).not.toBeNull();
    expect(workspace?.style.getPropertyValue("--wiki-tree-width")).toBe("328px");

    const separator = screen.getByRole("separator", { name: "调整 Wiki 目录宽度" });
    fireEvent.mouseDown(separator, { clientX: 328 });
    fireEvent.mouseMove(document, { clientX: 448 });
    fireEvent.mouseUp(document, { clientX: 448 });

    expect(workspace?.style.getPropertyValue("--wiki-tree-width")).toBe("448px");
  });

  it("keeps the editor visible after expanding and collapsing the tree in edit mode", async () => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703&mode=edit");

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
        if (path === "/api/wiki/documents/703") {
          return jsonResponse({
            document_id: 1703,
            node_id: 703,
            title: "支付接入说明",
            current_version_id: 2703,
            current_body_markdown: "# 支付接入说明\n\n正文。",
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
                body_markdown: "# 支付接入说明\n\n正文。",
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

    expect(await screen.findByText("Markdown 源码")).toBeInTheDocument();
    await waitFor(() => {
      expect(document.querySelector(".wiki-pane-resizer-spacer")).not.toBeNull();
    });

    fireEvent.mouseDown(screen.getByRole("button", { name: "展开 Wiki 目录" }), {
      clientX: 0,
    });
    fireEvent.mouseUp(document, { clientX: 0 });
    expect(await screen.findByRole("separator", { name: "调整 Wiki 目录宽度" })).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("button", { name: "收起 Wiki 目录" }), {
      clientX: 0,
    });
    fireEvent.mouseUp(document, { clientX: 0 });

    await waitFor(() => {
      expect(document.querySelector(".wiki-pane-resizer-spacer")).toBeInTheDocument();
      expect(document.querySelector(".wiki-source-editor")).toBeInTheDocument();
    });
  });
});
