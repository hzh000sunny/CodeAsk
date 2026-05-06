import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type { WikiSourceRead } from "../src/types/wiki";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki sources workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=705");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("creates, edits, and syncs wiki sources from the standalone wiki workbench", async () => {
    let sources: WikiSourceRead[] = [
      {
        id: 31,
        space_id: 70,
        kind: "directory_import",
        display_name: "Payment Runbooks",
        uri: "file:///srv/wiki/payment",
        metadata_json: { root_path: "docs/payment" },
        status: "active",
        last_synced_at: null,
        created_at: "2026-05-01T10:00:00",
        updated_at: "2026-05-01T10:00:00",
      },
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
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
        if (path === "/api/wiki/documents/705") {
          return jsonResponse({
            document_id: 1705,
            node_id: 705,
            title: "Runbook",
            current_version_id: 2705,
            current_body_markdown: "# Runbook\n\n这里是知识库正文。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: { source: "manual_upload" },
            permissions: { read: true, write: true, admin: true },
          });
        }
        if (path === "/api/wiki/documents/705/versions") {
          return jsonResponse({
            versions: [
              {
                id: 2705,
                document_id: 1705,
                version_no: 1,
                body_markdown: "# Runbook\n\n这里是知识库正文。",
                created_by_subject_id: "client_test",
                created_at: "2026-04-30T10:00:00",
                updated_at: "2026-04-30T10:00:00",
              },
            ],
          });
        }
        if (path === "/api/wiki/sources?space_id=70") {
          return jsonResponse({ items: sources });
        }
        if (path === "/api/wiki/sources" && init?.method === "POST") {
          const payload = JSON.parse(String(init.body)) as {
            kind: WikiSourceRead["kind"];
            display_name: string;
            uri: string | null;
            metadata_json: WikiSourceRead["metadata_json"];
          };
          const created: WikiSourceRead = {
            id: 32,
            space_id: 70,
            kind: payload.kind,
            display_name: payload.display_name,
            uri: payload.uri,
            metadata_json: payload.metadata_json,
            status: "active",
            last_synced_at: null,
            created_at: "2026-05-02T10:00:00",
            updated_at: "2026-05-02T10:00:00",
          };
          sources = [...sources, created];
          return jsonResponse(created, 201);
        }
        if (path === "/api/wiki/sources/32" && init?.method === "PUT") {
          const payload = JSON.parse(String(init.body)) as {
            display_name?: string;
            uri?: string | null;
            metadata_json?: WikiSourceRead["metadata_json"];
            status?: WikiSourceRead["status"];
          };
          sources = sources.map((item) =>
            item.id === 32
              ? {
                  ...item,
                  display_name: payload.display_name ?? item.display_name,
                  uri: payload.uri ?? item.uri,
                  metadata_json: payload.metadata_json ?? item.metadata_json,
                  status: payload.status ?? item.status,
                }
              : item,
          );
          return jsonResponse(sources.find((item) => item.id === 32));
        }
        if (path === "/api/wiki/sources/32/sync" && init?.method === "POST") {
          sources = sources.map((item) =>
            item.id === 32
              ? {
                  ...item,
                  last_synced_at: "2026-05-03T10:00:00",
                  updated_at: "2026-05-03T10:00:00",
                }
              : item,
          );
          return jsonResponse(sources.find((item) => item.id === 32));
        }
        throw new Error(`Unhandled request: ${path} ${init?.method ?? "GET"}`);
      }),
    );

    render(<App />);

    await screen.findByRole("button", { name: "更多" });

    fireEvent.click(screen.getByRole("button", { name: "更多" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "来源治理" }));

    const dialog = await screen.findByRole("dialog", { name: "来源治理" });
    expect(await within(dialog).findByText("Payment Runbooks")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "添加来源" }));

    const createForm = within(dialog).getByRole("form", { name: "来源表单" });
    fireEvent.change(within(createForm).getByLabelText("来源名称"), {
      target: { value: "On-call Notes" },
    });
    fireEvent.change(within(createForm).getByLabelText("来源类型"), {
      target: { value: "manual_upload" },
    });
    fireEvent.change(within(createForm).getByLabelText("URI / 路径"), {
      target: { value: "file:///srv/wiki/oncall" },
    });
    fireEvent.change(within(createForm).getByLabelText("附加元数据"), {
      target: { value: '{\"root_path\":\"notes/oncall\"}' },
    });
    fireEvent.click(within(createForm).getByRole("button", { name: "保存来源" }));

    await waitFor(() => {
      expect(within(dialog).getByText("On-call Notes")).toBeInTheDocument();
    });

    const createdRow = within(dialog).getByTestId("wiki-source-row-32");
    fireEvent.click(within(createdRow).getByRole("button", { name: "编辑来源" }));

    const editForm = within(dialog).getByRole("form", { name: "来源表单" });
    fireEvent.change(within(editForm).getByLabelText("来源名称"), {
      target: { value: "On-call Notes Mirror" },
    });
    fireEvent.click(within(editForm).getByRole("button", { name: "保存来源" }));

    await waitFor(() => {
      expect(within(dialog).getByText("On-call Notes Mirror")).toBeInTheDocument();
    });

    fireEvent.click(within(createdRow).getByRole("button", { name: "同步来源" }));

    await waitFor(() => {
      expect(within(createdRow).getByText("刚刚同步")).toBeInTheDocument();
    });
  });
});
