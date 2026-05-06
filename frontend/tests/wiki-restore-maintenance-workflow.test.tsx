import {
  fireEvent,
  render,
  screen,
  waitFor,
  waitForElementToBeRemoved,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki restore and maintenance workflow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
  });

  it("offers restore after deleting a wiki node and brings the document back", async () => {
    let deleted = false;

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
              ...(deleted
                ? []
                : [
                    {
                      id: 703,
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
                  ]),
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
            title: "Runbook",
            current_version_id: 2703,
            current_body_markdown: "# Runbook\n\n正文。",
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
                body_markdown: "# Runbook\n\n正文。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/nodes/703" && init?.method === "DELETE") {
          deleted = true;
          return new Response(null, { status: 204 });
        }
        if (path === "/api/wiki/nodes/703/restore" && init?.method === "POST") {
          deleted = false;
          return jsonResponse({
            id: 703,
            space_id: 70,
            feature_id: 7,
            parent_id: 701,
            type: "document",
            name: "Runbook",
            path: "knowledge-base/runbook",
            system_role: null,
            sort_order: 0,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-05-01T10:00:00",
          });
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });
    expect(await screen.findByText("正文。")).toBeInTheDocument();

    fireEvent.click(
      await within(treePane).findByRole("button", { name: /打开节点 Runbook 的更多操作/ }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    const deleteDialog = await screen.findByRole("dialog");
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "确认删除" }));

    await waitForElementToBeRemoved(() => screen.queryByRole("dialog", { name: "删除 Wiki 节点" }));
    const restoreDialog = await screen.findByRole("dialog", { name: "Wiki 节点已删除，可恢复" });
    expect(within(restoreDialog).getByText("Wiki 节点已删除，可恢复")).toBeInTheDocument();
    fireEvent.click(within(restoreDialog).getByRole("button", { name: "恢复节点" }));

    await waitFor(() => {
      expect(within(treePane).getByRole("button", { name: "Runbook" })).toBeInTheDocument();
    });
    expect(await screen.findByText("Wiki 节点已恢复")).toBeInTheDocument();
    expect(await screen.findByText("正文。")).toBeInTheDocument();
  });

  it("restores an archived feature and triggers manual reindex from the tree menu", async () => {
    let restored = false;

    window.history.replaceState(null, "", "/#/wiki?feature=8&node=-100008");

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "admin",
            display_name: "Admin",
            role: "admin",
            authenticated: true,
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
              name: "历史特性",
              slug: "history-feature",
              description: "已归档特性",
              owner_subject_id: "client_test",
              summary_text: null,
              created_at: "2026-04-29T10:00:00",
              updated_at: "2026-04-29T10:00:00",
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
                id: -100008,
                space_id: 80,
                feature_id: 8,
                parent_id: restored ? -1 : -2,
                type: "folder",
                name: "历史特性",
                path: restored ? "当前特性/history-feature" : "历史特性/history-feature",
                system_role: restored ? "feature_space_current" : "feature_space_history",
                sort_order: 0,
                created_at: "2026-04-29T10:00:00",
                updated_at: "2026-05-01T10:00:00",
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
                created_at: "2026-04-29T10:00:00",
                updated_at: "2026-05-01T10:00:00",
              },
              {
                id: 803,
                space_id: 80,
                feature_id: 8,
                parent_id: 801,
                type: "document",
                name: "Archived Runbook",
                path: "knowledge-base/archived-runbook",
                system_role: null,
                sort_order: 0,
                created_at: "2026-04-29T10:00:00",
                updated_at: "2026-05-01T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/spaces/by-feature/8") {
          return jsonResponse({
            id: 80,
            feature_id: 8,
            scope: restored ? "current" : "history",
            display_name: "历史特性",
            slug: "history-feature",
            status: restored ? "active" : "archived",
            created_at: "2026-04-29T10:00:00",
            updated_at: "2026-05-01T10:00:00",
          });
        }
        if (path === "/api/wiki/reports/projections?feature_id=8") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/spaces/80/restore" && init?.method === "POST") {
          restored = true;
          return jsonResponse({
            id: 80,
            feature_id: 8,
            scope: "current",
            display_name: "历史特性",
            slug: "history-feature",
            status: "active",
            created_at: "2026-04-29T10:00:00",
            updated_at: "2026-05-01T10:10:00",
          });
        }
        if (path === "/api/wiki/maintenance/nodes/801/reindex" && init?.method === "POST") {
          return jsonResponse({
            root_node_id: 801,
            reindexed_documents: 2,
          });
        }
        if (path === "/api/wiki/documents/803") {
          return jsonResponse({
            document_id: 1803,
            node_id: 803,
            title: "Archived Runbook",
            current_version_id: 2803,
            current_body_markdown: "# Archived Runbook\n\n历史正文。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "manual_create" },
            permissions: { read: true, write: true, admin: true },
          });
        }
        if (path === "/api/wiki/documents/803/versions") {
          return jsonResponse({
            versions: [
              {
                id: 2803,
                document_id: 1803,
                version_no: 1,
                body_markdown: "# Archived Runbook\n\n历史正文。",
                created_by_subject_id: "admin",
                created_at: "2026-04-29T10:00:00",
                updated_at: "2026-05-01T10:00:00",
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

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });

    fireEvent.click(
      await within(treePane).findByRole("button", { name: /打开节点 历史特性 的更多操作/ }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "恢复特性" }));

    const restoreDialog = await screen.findByRole("dialog");
    fireEvent.click(within(restoreDialog).getByRole("button", { name: "确认恢复" }));

    expect(await screen.findByText("历史特性已恢复")).toBeInTheDocument();

    fireEvent.click(
      await within(treePane).findByRole("button", { name: /打开节点 知识库 的更多操作/ }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "重新索引" }));

    const reindexDialog = await screen.findByRole("dialog");
    fireEvent.click(within(reindexDialog).getByRole("button", { name: "确认重新索引" }));

    expect(await screen.findByText("已重新索引 2 篇文档")).toBeInTheDocument();
  });
});
