import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// 树结构：-1 当前特性(feature_group_current，顶层) → -100007 支付结算(feature_space)
//        → 701 知识库(knowledge_base) → 703 支付接入说明(document)
function stubWikiFetch() {
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
}

describe("Wiki default selection workflow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("冷启动(URL 无 feature/node):空正文、特性闭合、不高亮、不自动选中任何文档", async () => {
    // 真·冷启动：URL 不带任何 feature/node，特性由兜底回落得到、并非用户主动选择。
    window.history.replaceState(null, "", "/#/wiki");
    stubWikiFetch();

    render(<App />);

    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).not.toBeNull();
    });

    // 顶层特性可见，但特性是闭合的：知识库不渲染、第一篇文档不被自动选中。
    const feature = await screen.findByRole("button", { name: "支付结算" });
    expect(screen.queryByText("知识库")).toBeNull();
    expect(screen.queryByText("正文。")).toBeNull();
    // 冷启动不主动高亮兜底特性。
    expect(feature).not.toHaveAttribute("data-active-feature", "true");

    // 正文区落到「引导选择」空态，而非渲染某篇文档。
    expect(screen.getByText("选择一篇 Wiki 查看")).toBeInTheDocument();
    // 回归护栏：未选中任何特性/文档时，绝不出现「开始建设这个特性」这类误导文案。
    expect(screen.queryByText(/开始建设/)).toBeNull();
  });

  it("从特性页带特性进入(feature=X, 无 node):树里高亮并展开该特性", async () => {
    // 显式带特性进入（特性页跳转 / 深链）：即便没选具体文档，也要在树里点亮该特性，
    // 让用户一眼看出对应哪个特性，而不是右栏写着特性名、左栏却毫无指向。
    window.history.replaceState(null, "", "/#/wiki?feature=7");
    stubWikiFetch();

    render(<App />);

    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).not.toBeNull();
    });

    // 该特性根被高亮（区别于文档选中的 data-active-feature 标记）。
    const feature = await screen.findByRole("button", { name: "支付结算" });
    await waitFor(() => {
      expect(feature).toHaveAttribute("data-active-feature", "true");
    });
    // 该特性被展开：其下的知识库可见。
    expect(await screen.findByText("知识库")).toBeInTheDocument();
  });

  it("新特性(无任何文档)带特性进入:高亮特性 + 右栏点名「开始建设」", async () => {
    // 用户报告的精确场景：新建特性还没有任何 Wiki，从特性页知识库点进来——
    // 右栏点名「开始建设「<特性名>」的 Wiki」，左侧树也要选中并展开对应特性。
    window.history.replaceState(null, "", "/#/wiki?feature=7");
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
          // 特性下只有空的知识库目录，没有任何文档。
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
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );

    render(<App />);

    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).not.toBeNull();
    });

    // 右栏点名是哪个特性，回答「给谁建设」。
    expect(
      await screen.findByText("开始建设「支付结算」的 Wiki"),
    ).toBeInTheDocument();
    // 左侧树同步选中并展开该特性。
    const feature = await screen.findByRole("button", { name: "支付结算" });
    await waitFor(() => {
      expect(feature).toHaveAttribute("data-active-feature", "true");
    });
    expect(await screen.findByText("知识库")).toBeInTheDocument();
  });

  it("URL 携带 node(刷新/切页回来):该文档仍被选中并渲染，祖先链展开", async () => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
    stubWikiFetch();

    render(<App />);

    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).not.toBeNull();
    });

    // 选中被保留：文档正文渲染出来（"正文。"只出现在已渲染的文档体内）。
    expect(await screen.findByText("正文。")).toBeInTheDocument();
    // 祖先链展开：知识库节点可见。
    expect(await screen.findByText("知识库")).toBeInTheDocument();
    // 不应落到空状态。
    expect(
      screen.queryByText("选择一篇 Wiki 查看"),
    ).toBeNull();
  });

  it("选中文档后切到其它页面再切回 Wiki:选中仍被保留", async () => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
    stubWikiFetch();

    render(<App />);

    // 进入即选中 703，正文渲染。
    expect(await screen.findByText("正文。")).toBeInTheDocument();

    // 切到「会话」页：Wiki 工作区卸载。
    fireEvent.click(screen.getByRole("button", { name: "会话" }));
    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).toBeNull();
    });

    // 切回「Wiki」：之前选中的文档应当仍然被选中并渲染（内存态保留）。
    fireEvent.click(screen.getByRole("button", { name: "Wiki" }));
    expect(await screen.findByText("正文。")).toBeInTheDocument();
    expect(
      screen.queryByText("选择一篇 Wiki 查看"),
    ).toBeNull();
  });

  it("选中文档后切到其它页面、刷新浏览器、再回到 Wiki:选中仍被恢复(localStorage 补水)", async () => {
    window.history.replaceState(null, "", "/#/wiki?feature=7&node=703");
    stubWikiFetch();

    const first = render(<App />);
    // 进入即选中 703 并渲染，选中被持久化到 localStorage。
    expect(await screen.findByText("正文。")).toBeInTheDocument();

    // 切到「会话」页：URL 变成 #/sessions，不再携带 wiki 的 node 参数。
    fireEvent.click(screen.getByRole("button", { name: "会话" }));
    await waitFor(() => {
      expect(document.querySelector(".wiki-workspace")).toBeNull();
    });
    expect(window.location.hash).toBe("#/sessions");

    // 模拟刷新浏览器：卸载并以「刷新时的 URL」(#/sessions，无 wiki 参数) 重新挂载。
    first.unmount();
    stubWikiFetch();
    window.history.replaceState(null, "", "/#/sessions");
    render(<App />);

    // 回到 Wiki：尽管 URL 里没有 node，仍应从 localStorage 恢复到之前选中的那篇。
    fireEvent.click(screen.getByRole("button", { name: "Wiki" }));
    expect(await screen.findByText("正文。")).toBeInTheDocument();
    expect(
      screen.queryByText("选择一篇 Wiki 查看"),
    ).toBeNull();
  });
});
