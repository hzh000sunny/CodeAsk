import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki search workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("keeps the matched heading in the wiki hash route after selecting a search result", async () => {
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
            display_name: "payment-settlement",
            slug: "payment-settlement",
            status: "active",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          });
        }
        if (path === "/api/wiki/reports/projections?feature_id=7") {
          return jsonResponse({ items: [] });
        }
        if (path === "/api/wiki/documents/703") {
          return jsonResponse({
            document_id: 88,
            node_id: 703,
            title: "支付接入说明",
            current_version_id: 1,
            current_body_markdown: "# 支付接入说明\n\n## 排查步骤\n\n先确认配置。",
            draft_body_markdown: null,
            index_status: "ready",
            broken_refs_json: { links: [], assets: [] },
            resolved_refs_json: [],
            provenance_json: null,
            permissions: { read: true, write: true, admin: false },
          });
        }
        if (path === "/api/wiki/documents/703/versions") {
          return jsonResponse({ versions: [] });
        }
        if (
          path ===
          "/api/wiki/search?q=%E6%8E%A5%E5%85%A5&limit=20&current_feature_id=7"
        ) {
          return jsonResponse({
            items: [
              {
                kind: "document",
                node_id: 703,
                title: "支付接入说明",
                path: "knowledge-base/payment-access",
                heading_path: "支付接入说明 > 排查步骤",
                feature_id: 7,
                group_key: "current_feature",
                group_label: "当前特性",
                snippet: "先确认配置。",
                score: 4,
                document_id: 88,
                report_id: null,
              },
            ],
          });
        }
        throw new Error(`unexpected request ${path}`);
      }),
    );

    render(<App />);

    const treeRegion = await screen.findByRole("complementary", {
      name: "Wiki 目录树",
    });
    fireEvent.change(within(treeRegion).getByPlaceholderText("搜索"), {
      target: { value: "接入" },
    });

    const result = await screen.findByRole("button", { name: /支付接入说明/ });
    expect(within(result).getByText("知识库 / 支付接入说明")).toBeInTheDocument();
    expect(within(result).getByText("支付接入说明 > 排查步骤")).toBeInTheDocument();
    fireEvent.click(result);

    await waitFor(() => {
      const query = window.location.hash.split("?")[1] ?? "";
      const params = new URLSearchParams(query);
      expect(params.get("heading")).toBe("支付接入说明 > 排查步骤");
    });
  });
});
