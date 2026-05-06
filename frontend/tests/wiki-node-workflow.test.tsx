import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki node workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("renames and deletes a wiki document from the tree menu", async () => {
    let documentName = "Runbook";
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
                      name: documentName,
                      path: `knowledge-base/${documentName.toLowerCase().replaceAll(" ", "-")}`,
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
            title: documentName,
            current_version_id: 2703,
            current_body_markdown: `# ${documentName}\n\n正文。`,
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
                body_markdown: `# ${documentName}\n\n正文。`,
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/nodes/703" && init?.method === "PUT") {
          const payload = JSON.parse(String(init.body)) as { name?: string };
          if (payload.name) {
            documentName = payload.name;
          }
          return jsonResponse({
            id: 703,
            space_id: 70,
            feature_id: 7,
            parent_id: 701,
            type: "document",
            name: documentName,
            path: `knowledge-base/${documentName.toLowerCase().replaceAll(" ", "-")}`,
            system_role: null,
            sort_order: 0,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          });
        }
        if (path === "/api/wiki/nodes/703" && init?.method === "DELETE") {
          deleted = true;
          return new Response(null, { status: 204 });
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
      await within(treePane).findByRole("button", {
        name: /打开节点 Runbook 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "重命名" }));

    const renameDialog = await screen.findByRole("dialog");
    fireEvent.change(within(renameDialog).getByRole("textbox"), {
      target: { value: "Runbook Updated" },
    });
    fireEvent.click(within(renameDialog).getByRole("button", { name: "保存名称" }));

    expect(await screen.findByText("Wiki 节点已重命名")).toBeInTheDocument();
    expect(
      await screen.findByText("Runbook Updated", { selector: ".wiki-page-header h1" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("知识库 / Runbook Updated", { selector: ".wiki-page-header p" }),
    ).toBeInTheDocument();
    expect(
      await within(treePane).findByRole("button", { name: "Runbook Updated" }),
    ).toBeInTheDocument();

    fireEvent.click(
      await within(treePane).findByRole("button", {
        name: /打开节点 Runbook Updated 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    const deleteDialog = await screen.findByRole("dialog");
    expect(within(deleteDialog).getByText("删除 Wiki 节点")).toBeInTheDocument();
    expect(
      within(deleteDialog).getByText(
        "确认删除“Runbook Updated”？其下游子节点会一起进入软删除状态。",
      ),
    ).toBeInTheDocument();
    expect(within(deleteDialog).getByText("知识库 / Runbook Updated")).toBeInTheDocument();
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("Wiki 节点已删除")).toBeInTheDocument();
    await waitFor(() => {
      expect(
        within(treePane).queryByRole("button", { name: "Runbook Updated" }),
      ).not.toBeInTheDocument();
    });
    expect(
      await screen.findByText("当前特性还没有 Wiki 文档，或当前选择的节点不是文档。"),
    ).toBeInTheDocument();
  });

  it("clears the knowledge base root contents without deleting the root itself", async () => {
    let documentDeleted = false;
    const deletedNodeIds: number[] = [];

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
              ...(documentDeleted
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
        if (path === "/api/reports?feature_id=7") {
          return jsonResponse([]);
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
          deletedNodeIds.push(703);
          documentDeleted = true;
          return new Response(null, { status: 204 });
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
      await within(treePane).findByRole("button", {
        name: /打开节点 知识库 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    const deleteDialog = await screen.findByRole("dialog");
    expect(within(deleteDialog).getByText("清空目录内容")).toBeInTheDocument();
    expect(within(deleteDialog).getByText("知识库")).toBeInTheDocument();
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "确认清空" }));

    expect(await screen.findByText("目录内容已清空")).toBeInTheDocument();
    expect(deletedNodeIds).toEqual([703]);
    expect(screen.queryByText("正文。")).not.toBeInTheDocument();
    expect(await within(treePane).findByRole("button", { name: "知识库" })).toBeInTheDocument();
    expect(within(treePane).queryByRole("button", { name: "Runbook" })).not.toBeInTheDocument();
  });

  it("closes the delete dialog immediately after delete succeeds even when tree refresh is slow", async () => {
    let deleted = false;
    const refreshGate: { release: (() => void) | null } = { release: null };
    let treeRequests = 0;

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
          treeRequests += 1;
          if (treeRequests > 1 && deleted) {
            await new Promise<void>((resolve) => {
              refreshGate.release = resolve;
            });
          }
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
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });
    fireEvent.click(
      await within(treePane).findByRole("button", {
        name: /打开节点 Runbook 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    const deleteDialog = await screen.findByRole("dialog");
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("Wiki 节点已删除")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    const releaseTreeRefresh = refreshGate.release;
    if (releaseTreeRefresh) {
      releaseTreeRefresh();
    }
  });

  it("shows the feature display name when clearing a feature root", async () => {
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
              name: "小米",
              slug: "feature",
              description: "小米知识域",
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
                path: "当前特性/feature",
                system_role: "feature_space_current",
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
            display_name: "小米",
            slug: "feature",
            status: "ready",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          });
        }
        if (path === "/api/wiki/reports/projections?feature_id=7") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/reports?feature_id=7") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    window.history.replaceState(null, "", "/#/wiki?feature=7&node=-100007");

    render(<App />);

    const treePane = await screen.findByRole("complementary", { name: "Wiki 目录树" });

    fireEvent.click(
      await within(treePane).findByRole("button", {
        name: /打开节点 小米 的更多操作/,
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    const deleteDialog = await screen.findByRole("dialog");
    expect(within(deleteDialog).getByText("清空目录内容")).toBeInTheDocument();
    expect(within(deleteDialog).getByText("小米")).toBeInTheDocument();
    expect(within(deleteDialog).queryByText("当前特性 / feature")).not.toBeInTheDocument();
  });
});
