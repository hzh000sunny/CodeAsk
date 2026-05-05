import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Wiki edit leave workflow", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  function stubWikiFetchWithDrafts() {
    let draftBody: string | null = null;

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
      if (path === "/api/wiki/documents/703") {
        return jsonResponse({
          document_id: 1703,
          node_id: 703,
          title: "Runbook",
          current_version_id: 2703,
          current_body_markdown: "# Runbook\n\n正式内容。",
          draft_body_markdown: draftBody,
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
              body_markdown: "# Runbook\n\n正式内容。",
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/documents/703/draft" && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body)) as { body_markdown: string };
        draftBody = payload.body_markdown;
        return jsonResponse({
          document_id: 1703,
          node_id: 703,
          title: "Runbook",
          current_version_id: 2703,
          current_body_markdown: "# Runbook\n\n正式内容。",
          draft_body_markdown: draftBody,
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("confirms before leaving edit mode and restores the saved draft", async () => {
    const fetchMock = stubWikiFetchWithDrafts();

    render(<App />);

    expect(await screen.findByText("正式内容。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));

    const editor = document.querySelector(".wiki-source-editor") as HTMLTextAreaElement | null;
    expect(editor).not.toBeNull();
    fireEvent.change(editor as HTMLTextAreaElement, {
      target: { value: "# Runbook\n\n正式内容。\n\n保留草稿" },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/wiki/documents/703/draft",
        expect.objectContaining({ method: "PUT" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "继续编辑" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保留草稿并离开" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "丢弃草稿" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存并离开" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保留草稿并离开" }));
    await screen.findByText("正式内容。");

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));

    await waitFor(() => {
      const nextEditor = document.querySelector(".wiki-source-editor") as HTMLTextAreaElement | null;
      expect(nextEditor?.value).toContain("保留草稿");
    });
  });

  it("seeds the editor from the current document and does not autosave unchanged content", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
      if (path === "/api/wiki/documents/703") {
        return jsonResponse({
          document_id: 1703,
          node_id: 703,
          title: "Runbook",
          current_version_id: 2703,
          current_body_markdown: "# Runbook\n\n正式内容。",
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
              body_markdown: "# Runbook\n\n正式内容。",
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
      if (path === "/api/wiki/documents/703/draft" && init?.method === "PUT") {
        return jsonResponse({
          document_id: 1703,
          node_id: 703,
          title: "Runbook",
          current_version_id: 2703,
          current_body_markdown: "# Runbook\n\n正式内容。",
          draft_body_markdown: "# Runbook\n\n正式内容。",
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: { source: "manual_create" },
          permissions: { read: true, write: true, admin: false },
        });
      }
      return jsonResponse({});
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("正式内容。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));

    await waitFor(() => {
      const editor = document.querySelector(".wiki-source-editor") as HTMLTextAreaElement | null;
      expect(editor?.value).toBe("# Runbook\n\n正式内容。");
    });

    await new Promise((resolve) => window.setTimeout(resolve, 950));

    const draftCalls = fetchMock.mock.calls.filter(
      ([input, init]) =>
        String(input) === "/api/wiki/documents/703/draft" && init?.method === "PUT",
    );
    expect(draftCalls).toHaveLength(0);
  });

  it("restores the expanded tree after leaving edit mode when it was expanded before editing", async () => {
    stubWikiFetchWithDrafts();

    render(<App />);

    expect(await screen.findByPlaceholderText("搜索")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "编辑" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(screen.queryByPlaceholderText("搜索")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("搜索")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "收起 Wiki 目录" })).toBeInTheDocument();
    });
  });

  it("keeps the tree collapsed after leaving edit mode when it was collapsed before editing", async () => {
    stubWikiFetchWithDrafts();

    render(<App />);

    expect(await screen.findByRole("button", { name: "收起 Wiki 目录" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "编辑" })).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("button", { name: "收起 Wiki 目录" }), {
      clientX: 0,
    });
    fireEvent.mouseUp(document, { clientX: 0 });

    await waitFor(() => {
      expect(screen.queryByPlaceholderText("搜索")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "展开 Wiki 目录" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() => {
      expect(screen.queryByPlaceholderText("搜索")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "展开 Wiki 目录" })).toBeInTheDocument();
    });
  });

  it("shows a centered save toast after saving from the editor", async () => {
    stubWikiFetchWithDrafts();

    render(<App />);

    expect(await screen.findByRole("button", { name: "编辑" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByRole("status")).toHaveTextContent("保存成功");
  });
});
