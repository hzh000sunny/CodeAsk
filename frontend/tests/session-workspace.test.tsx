import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import { queryClient } from "../src/lib/query-client";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function streamResponse(text: string) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: retrieval_context\ndata: {"feature_candidates":[],"wiki_hits":[],"report_hits":[]}\n\n',
          ),
        );
        controller.enqueue(
          encoder.encode(`event: text_delta\ndata: {"text":"${text}"}\n\n`),
        );
        controller.enqueue(
          encoder.encode('event: done\ndata: {"turn_id":"turn_stream"}\n\n'),
        );
        controller.close();
      },
    }),
    {
      headers: {
        "Content-Type": "text/event-stream",
      },
    },
  );
}

function transparencyStreamResponse() {
  const encoder = new TextEncoder();
  const chunks = [
    'event: scope_detection\ndata: {"feature_ids":[7,9],"confidence":0.82,"reason":"日志命中支付特性"}\n\n',
    'event: assistant_action\ndata: {"action":"评估证据","summary":"缺少启动参数，需要继续补充上下文"}\n\n',
    'event: tool_call\ndata: {"tool_call_id":"call_1","tool_name":"search_wiki","arguments_summary":{"query":"启动失败"}}\n\n',
    'event: tool_result\ndata: {"tool_call_id":"call_1","tool_name":"search_wiki","ok":true,"summary":"命中 2 条 Wiki","evidence_refs":[{"type":"wiki","title":"启动手册","path":"知识库/启动手册"}]}\n\n',
    'event: evidence\ndata: {"item":{"id":"ev_1","source":"wiki","title":"启动手册","locator":"docs/start.md"}}\n\n',
    'event: ask_user\ndata: {"ask_id":"ask_1","question":"请补充完整启动日志","options":["上传日志"],"reason":"当前证据不足"}\n\n',
    'event: done\ndata: {"turn_id":"turn_transparency"}\n\n',
  ];
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      },
    }),
    {
      headers: {
        "Content-Type": "text/event-stream",
      },
    },
  );
}

function emptyAttachmentListResponse(
  input: RequestInfo | URL,
  init?: RequestInit,
) {
  const path = String(input);
  if (
    /^\/api\/sessions\/[^/]+\/turns$/.test(path) &&
    (!init?.method || init.method === "GET")
  ) {
    return jsonResponse([]);
  }
  if (
    /^\/api\/sessions\/[^/]+\/traces$/.test(path) &&
    (!init?.method || init.method === "GET")
  ) {
    return jsonResponse([]);
  }
  if (
    /^\/api\/sessions\/[^/]+\/attachments$/.test(path) &&
    (!init?.method || init.method === "GET")
  ) {
    return jsonResponse([]);
  }
  return null;
}

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_test",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

describe("SessionWorkspace streaming interaction", () => {
  it("restores the selected session from the URL hash after reload", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "第一个会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: "sess_2",
              title: "第二个会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T09:00:00",
              updated_at: "2026-04-30T09:00:00",
            },
          ]);
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState(null, "", "/#/sessions?session=sess_2");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "第二个会话" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "第二个会话" }).closest(".list-row"),
    ).toHaveAttribute("data-active", "true");
  });

  it("keeps the selected session when leaving and returning to the sessions page", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "第一个会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: "sess_2",
              title: "第二个会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T09:00:00",
              updated_at: "2026-04-30T09:00:00",
            },
          ]);
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    window.history.replaceState(null, "", "/#/sessions");

    render(<App />);

    await screen.findByRole("heading", { name: "第一个会话" });
    fireEvent.click(screen.getByRole("button", { name: "第二个会话" }));

    expect(window.location.hash).toBe("#/sessions?session=sess_2");
    expect(
      await screen.findByRole("heading", { name: "第二个会话" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findByPlaceholderText("搜索特性")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "会话" }));

    expect(window.location.hash).toBe("#/sessions?session=sess_2");
    expect(
      await screen.findByRole("heading", { name: "第二个会话" }),
    ).toBeInTheDocument();
  });

  it("drops locally remembered sessions when the server list no longer includes them", async () => {
    let listCalls = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions" && (!init?.method || init.method === "GET")) {
          listCalls += 1;
          return jsonResponse([]);
        }
        if (path === "/api/sessions" && init?.method === "POST") {
          return jsonResponse(
            {
              id: "sess_created",
              title: "新的研发会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = await screen.findByRole("region", { name: "会话列表" });
    expect(await within(sessionList).findByText("暂无会话")).toBeInTheDocument();

    fireEvent.click(
      within(sessionList).getByRole("button", { name: "新建会话" }),
    );

    const createdTitle = await within(sessionList).findByText("新的研发会话");
    expect(createdTitle).toBeInTheDocument();
    expect(createdTitle).toHaveClass("item-title-text");

    await queryClient.invalidateQueries({ queryKey: ["sessions"] });

    await waitFor(() =>
      expect(
        within(sessionList).queryByText("新的研发会话"),
      ).not.toBeInTheDocument(),
    );
    expect(listCalls).toBeGreaterThanOrEqual(2);
    expect(within(sessionList).getByText("暂无会话")).toBeInTheDocument();
  });

  it("deletes a session from the session list", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "线上启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: "sess_2",
              title: "支付回调超时",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T09:00:00",
              updated_at: "2026-04-30T09:00:00",
            },
          ]);
        }
        if (path === "/api/sessions/sess_1" && init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(
      await within(sessionList).findByText("线上启动失败"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(sessionList).getByRole("button", {
        name: "打开会话 线上启动失败 的更多操作",
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    expect(
      screen.getByRole("dialog", { name: "删除会话" }),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/sessions/sess_1",
      expect.objectContaining({ method: "DELETE" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() =>
      expect(
        within(sessionList).queryByText("线上启动失败"),
      ).not.toBeInTheDocument(),
    );
    expect(within(sessionList).getByText("支付回调超时")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/sess_1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("renders the session row action menu outside the scrollable list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const attachmentResponse = emptyAttachmentListResponse(input);
      if (attachmentResponse) {
        return attachmentResponse;
      }
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            id: "sess_1",
            title: "线上启动失败",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(
      await within(sessionList).findByText("线上启动失败"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(sessionList).getByRole("button", {
        name: "打开会话 线上启动失败 的更多操作",
      }),
    );

    const menu = screen.getByRole("menu");
    expect(menu.parentElement).toBe(document.body);
  });

  it("places report generation next to send controls instead of the conversation header", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const attachmentResponse = emptyAttachmentListResponse(input);
      if (attachmentResponse) {
        return attachmentResponse;
      }
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            id: "sess_1",
            title: "线上启动失败",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "线上启动失败",
    );
    const composer = screen.getByRole("region", { name: "会话输入操作区" });
    expect(
      within(composer).getByRole("button", { name: "生成报告" }),
    ).toBeInTheDocument();
    const header = document.querySelector(".page-header") as HTMLElement;
    expect(
      within(header).queryByRole("button", { name: "生成报告" }),
    ).not.toBeInTheDocument();

    const actionLabels = Array.from(
      composer.querySelectorAll("label,button"),
    ).map((node) => node.textContent?.trim());
    expect(actionLabels).not.toContain("强制代码调查");
    const rightActions = composer.querySelector(".composer-primary-actions");
    expect(rightActions).toBeInTheDocument();
    expect(
      within(rightActions as HTMLElement).getByRole("button", {
        name: "生成报告",
      }),
    ).toBeInTheDocument();
    expect(
      within(rightActions as HTMLElement).getByRole("button", { name: "发送" }),
    ).toBeInTheDocument();
    expect(actionLabels.indexOf("生成报告")).toBeLessThan(
      actionLabels.indexOf("发送"),
    );
  });

  it("blocks report generation until the session has a completed question and answer", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const attachmentResponse = emptyAttachmentListResponse(input);
      if (attachmentResponse) {
        return attachmentResponse;
      }
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            id: "sess_1",
            title: "线上启动失败",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ]);
      }
      if (path === "/api/features") {
        return jsonResponse([feature]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "线上启动失败",
    );
    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    expect(
      screen.getByRole("dialog", { name: "暂不能生成报告" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/至少完成一次问答/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/sessions/sess_1/reports",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("clears the action trace after deleting the only implicitly selected session", async () => {
    let deleted = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/sessions/sess_1/turns") {
          return jsonResponse([
            {
              id: "turn_1",
              session_id: "sess_1",
              turn_index: 0,
              role: "agent",
              content: "已读取小米病历。",
              evidence: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/sessions/sess_1/traces") {
          return jsonResponse([
            {
              id: "trace_1",
              session_id: "sess_1",
              turn_id: "turn_1",
              stage: "chat_runtime",
              event_type: "tool_result",
              payload: {
                tool_name: "search_wiki",
                ok: true,
                summary: "命中小米病历",
              },
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse(
            deleted
              ? []
              : [
                  {
                    id: "sess_1",
                    title: "告诉我小米病情的变化趋势",
                    created_by_subject_id: "client_test",
                    status: "active",
                    pinned: false,
                    created_at: "2026-04-30T10:00:00",
                    updated_at: "2026-04-30T10:00:00",
                  },
                ],
          );
        }
        if (path === "/api/sessions/sess_1" && init?.method === "DELETE") {
          deleted = true;
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(
      await within(sessionList).findByText("告诉我小米病情的变化趋势"),
    ).toBeInTheDocument();
    expect(await screen.findByText("命中小米病历")).toBeInTheDocument();

    fireEvent.click(
      within(sessionList).getByRole("button", {
        name: "打开会话 告诉我小米病情的变化趋势 的更多操作",
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() =>
      expect(
        within(sessionList).queryByText("告诉我小米病情的变化趋势"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("命中小米病历")).not.toBeInTheDocument();
    expect(
      screen.getByText("发送问题后，这里会展示模型实际使用的上下文和工具动作。"),
    ).toBeInTheDocument();
  });

  it("confirms report generation with a feature and links to the generated report", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/features") {
          return jsonResponse([feature]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return new Response(
            [
              'event: scope_detection\ndata: {"feature_ids":[7],"confidence":0.91,"reason":"命中支付特性"}',
              'event: text_delta\ndata: {"text":"检查配置缺失。"}',
              "event: done\ndata: {}",
            ].join("\n\n"),
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        if (
          path === "/api/sessions/sess_1/reports/prepare" &&
          init?.method === "POST"
        ) {
          return jsonResponse({
            request_id: "report_prepare_test",
            status: "running",
            draft: null,
            error: null,
          });
        }
        if (path === "/api/sessions/sess_1/reports/prepare/report_prepare_test") {
          return jsonResponse({
            request_id: "report_prepare_test",
            status: "succeeded",
            error: null,
            draft: {
              existing_report_id: null,
              feature_id: 7,
              inferred_feature_ids: [7],
              title: "2026-05-08 支付启动失败",
              body_markdown:
                "# 问题背景\n\n支付服务启动失败。\n\n# 分析\n\n检查配置缺失。",
            },
          });
        }
        if (
          path === "/api/sessions/sess_1/reports" &&
          init?.method === "POST"
        ) {
          return jsonResponse(
            {
              id: 42,
              feature_id: 7,
              title: "2026-05-08 支付启动失败",
              body_markdown: "# 问题背景\n\n支付服务启动失败。\n\n# 分析\n\n检查配置缺失。",
              metadata_json: { source: "session", session_id: "sess_1" },
              status: "draft",
              verified: false,
              verified_by: null,
              verified_at: null,
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        if (path === "/api/documents?feature_id=7") {
          return jsonResponse([]);
        }
        if (path === "/api/reports?feature_id=7") {
          return jsonResponse([
            {
              id: 42,
              feature_id: 7,
              title: "2026-05-08 支付启动失败",
              body_markdown:
                "# 问题背景\n\n支付服务启动失败。\n\n# 分析\n\n检查配置缺失。\n\n# 建议\n\n重启支付服务",
              metadata_json: { source: "session", session_id: "sess_1" },
              status: "draft",
              verified: false,
              verified_by: null,
              verified_at: null,
              created_by_subject_id: "client_test",
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/features/7/repos") {
          return jsonResponse({ repos: [] });
        }
        if (path === "/api/repos") {
          return jsonResponse({ repos: [] });
        }
        if (path === "/api/skills") {
          return jsonResponse([]);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "支付启动失败",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));
    expect(
      await screen.findByRole("dialog", { name: "生成问题定位报告" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("绑定特性")).toHaveValue("7");
    expect(screen.getByLabelText("报告标题")).toHaveValue(
      "2026-05-08 支付启动失败",
    );
    const [, prepareInit] = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/sessions/sess_1/reports/prepare" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(prepareInit.body))).toEqual({
      feature_id: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "保存报告" }));

    await waitFor(() => {
      const [, init] = fetchMock.mock.calls.find(
        ([path, options]) =>
          path === "/api/sessions/sess_1/reports" &&
          (options as RequestInit | undefined)?.method === "POST",
      ) as unknown as [string, RequestInit];
      expect(JSON.parse(String(init.body))).toMatchObject({
        feature_id: 7,
        title: "2026-05-08 支付启动失败",
        body_markdown: "# 问题背景\n\n支付服务启动失败。\n\n# 分析\n\n检查配置缺失。",
      });
    });
    expect(
      await screen.findByRole("dialog", { name: "报告已生成" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看报告" }));

    expect(
      await screen.findByRole("tab", { name: "问题报告", selected: true }),
    ).toBeInTheDocument();
    expect(
      await screen.findAllByText("2026-05-08 支付启动失败"),
    ).not.toHaveLength(0);
    expect(
      await screen.findByRole("button", { name: /2026-05-08 支付启动失败/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText("问题背景")).toBeInTheDocument();
    expect(await screen.findByText("分析")).toBeInTheDocument();
  });

  it("shows a preparing dialog immediately when report draft generation is pending", async () => {
    let resolveStatus: (value: Response) => void = () => undefined;
    const statusPromise = new Promise<Response>((resolve) => {
      resolveStatus = resolve;
    });
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/features") {
          return jsonResponse([feature]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return new Response(
            [
              'event: scope_detection\ndata: {"feature_ids":[7],"confidence":0.91,"reason":"命中支付特性"}',
              'event: text_delta\ndata: {"text":"检查配置缺失。"}',
              "event: done\ndata: {}",
            ].join("\n\n"),
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        if (
          path === "/api/sessions/sess_1/reports/prepare" &&
          init?.method === "POST"
        ) {
          return jsonResponse({
            request_id: "report_prepare_test",
            status: "running",
            draft: null,
            error: null,
          });
        }
        if (path === "/api/sessions/sess_1/reports/prepare/report_prepare_test") {
          return statusPromise;
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "支付启动失败",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    expect(
      await screen.findByRole("dialog", { name: "正在准备报告" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "准备中" })).toBeDisabled();
    const [, prepareInit] = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/sessions/sess_1/reports/prepare" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(
      new Headers(prepareInit.headers).get("X-CodeAsk-Request-Id"),
    ).toMatch(/^report_prepare_/);

    resolveStatus(
      jsonResponse({
        request_id: "report_prepare_test",
        status: "succeeded",
        error: null,
        draft: {
          existing_report_id: null,
          feature_id: 7,
          inferred_feature_ids: [7],
          title: "2026-05-08 支付启动失败",
          body_markdown:
            "# 问题背景\n\n支付服务启动失败。\n\n# 分析\n\n检查配置缺失。",
        },
      }),
    );

    expect(
      await screen.findByRole("dialog", { name: "生成问题定位报告" }),
    ).toBeInTheDocument();
  });

  it("recovers a prepared report when the long prepare request returns proxy 503", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/features") {
          return jsonResponse([feature]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return streamResponse("检查配置缺失。");
        }
        if (
          path === "/api/sessions/sess_1/reports/prepare" &&
          init?.method === "POST"
        ) {
          return new Response("", { status: 503 });
        }
        if (/^\/api\/sessions\/sess_1\/reports\/prepare\/report_prepare_/.test(path)) {
          return jsonResponse({
            request_id: path.split("/").at(-1),
            status: "succeeded",
            error: null,
            draft: {
              existing_report_id: null,
              feature_id: 7,
              inferred_feature_ids: [7],
              title: "2026-05-08 支付启动失败",
              body_markdown: "# 问题背景\n\n支付服务启动失败。",
            },
          });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "支付启动失败",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    expect(
      await screen.findByRole("dialog", { name: "生成问题定位报告" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("报告标题")).toHaveValue(
      "2026-05-08 支付启动失败",
    );
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("promotes a session attachment into wiki and opens the promoted node", async () => {
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
        return jsonResponse([
          {
            id: "sess_1",
            title: "线上启动失败",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00",
          },
        ]);
      }
      if (path === "/api/features") {
        return jsonResponse([feature]);
      }
      if (path === "/api/sessions/sess_1/turns") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_1/traces") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_1/attachments") {
        return jsonResponse([
          {
            id: "att_1",
            session_id: "sess_1",
            kind: "log",
            display_name: "db-node-a.log",
            original_filename: "db-node-a.log",
            aliases: [],
            reference_names: [],
            description: "数据库节点 A 原始日志",
            file_path: "/tmp/db-node-a.log",
            mime_type: "text/plain",
            size_bytes: 64,
            created_at: "2026-05-06T10:00:00",
            updated_at: "2026-05-06T10:00:00",
          },
        ]);
      }
      if (path === "/api/wiki/tree?feature_id=7") {
        return jsonResponse({
          space: {
            id: 70,
            feature_id: 7,
            scope: "current",
            display_name: "支付结算",
            slug: "payment-settlement",
            status: "ready",
            created_at: "2026-05-06T10:00:00",
            updated_at: "2026-05-06T10:00:00",
          },
          nodes: [
            {
              id: -100007,
              space_id: 70,
              feature_id: 7,
              parent_id: null,
              type: "folder",
              name: "支付结算",
              path: "payment-settlement",
              system_role: "feature_space_current",
              sort_order: 0,
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
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
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/wiki/promotions/session-attachment" && init?.method === "POST") {
        return jsonResponse(
          {
            node: {
              id: 702,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: "db-node-a",
              path: "knowledge-base/db-node-a",
              system_role: null,
              sort_order: 0,
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
            },
            document_id: 1702,
            source_id: 52,
          },
          201,
        );
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
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
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
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
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
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
            },
            {
              id: 702,
              space_id: 70,
              feature_id: 7,
              parent_id: 701,
              type: "document",
              name: "db-node-a",
              path: "knowledge-base/db-node-a",
              system_role: null,
              sort_order: 0,
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
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
          created_at: "2026-05-06T10:00:00",
          updated_at: "2026-05-06T10:00:00",
        });
      }
      if (path === "/api/wiki/reports/projections?feature_id=7") {
        return jsonResponse({ items: [] });
      }
      if (path === "/api/wiki/documents/702") {
        return jsonResponse({
          document_id: 1702,
          node_id: 702,
          title: "db-node-a",
          current_version_id: 2702,
          current_body_markdown: "ERROR payment timeout",
          draft_body_markdown: null,
          index_status: "ready",
          broken_refs_json: { links: [], assets: [] },
          resolved_refs_json: [],
          provenance_json: {
            source: "session_promotion",
            session_id: "sess_1",
            attachment_id: "att_1",
          },
          permissions: { read: true, write: true, admin: false },
        });
      }
      if (path === "/api/wiki/documents/702/versions") {
        return jsonResponse({
          versions: [
            {
              id: 2702,
              document_id: 1702,
              version_no: 1,
              body_markdown: "ERROR payment timeout",
              created_by_subject_id: "client_test",
              created_at: "2026-05-06T10:00:00",
              updated_at: "2026-05-06T10:00:00",
            },
          ],
        });
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    window.history.replaceState(null, "", "/#/sessions");
    render(<App />);

    const panel = await screen.findByRole("region", { name: "会话数据" });
    fireEvent.click(
      await within(panel).findByRole("button", { name: "晋级为 Wiki db-node-a.log" }),
    );

    const dialog = await screen.findByRole("dialog", { name: "晋级为 Wiki" });
    expect(within(dialog).getByDisplayValue("支付结算")).toBeInTheDocument();
    expect(await within(dialog).findByDisplayValue("知识库")).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("db-node-a")).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "确认晋级" }));

    const success = await screen.findByRole("dialog", { name: "已写入 Wiki" });
    fireEvent.click(within(success).getByRole("button", { name: "打开 Wiki" }));

    await screen.findByRole("complementary", { name: "Wiki 目录树" });
    expect(window.location.hash).toContain("/wiki");
    expect(window.location.hash).toContain("feature=7");
    expect(window.location.hash).toContain("node=702");
  });

  it("loads persisted session turns and runtime traces when rendering a saved session", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            id: "sess_9965",
            title: "GLM 调试会话",
            created_by_subject_id: "admin",
            status: "active",
            pinned: false,
            created_at: "2026-05-02T10:00:00",
            updated_at: "2026-05-02T10:05:00",
          },
        ]);
      }
      if (path === "/api/sessions/sess_9965/turns") {
        return jsonResponse([
          {
            id: "turn_user_1",
            session_id: "sess_9965",
            turn_index: 0,
            role: "user",
            content: "请完整分析 GLM 调试链路。",
            evidence: null,
            created_at: "2026-05-02T10:01:00",
            updated_at: "2026-05-02T10:01:00",
          },
          {
            id: "turn_agent_1",
            session_id: "sess_9965",
            turn_index: 1,
            role: "agent",
            content:
              '# 链路已经完成\n\n建议补齐前端历史渲染。\n\n```ts\nconst status = "ok";\n```',
            evidence: {
              items: [
                {
                  id: "ev_1",
                  type: "wiki_doc",
                  summary: "支付接入说明",
                  data: {
                    path: "知识库/支付接入说明",
                    heading_path: "支付接入说明 > 排查步骤",
                    feature_id: 7,
                    node_id: 703,
                  },
                },
              ],
            },
            created_at: "2026-05-02T10:05:00",
            updated_at: "2026-05-02T10:05:00",
          },
        ]);
      }
      if (path === "/api/sessions/sess_9965/traces") {
        return jsonResponse([
          {
            id: "tr_scope_enter",
            session_id: "sess_9965",
            turn_id: "turn_user_1",
            stage: "scope_detection",
            event_type: "stage_enter",
            payload: { context: { question: "请完整分析 GLM 调试链路。" } },
            created_at: "2026-05-02T10:02:00",
            updated_at: "2026-05-02T10:02:00",
          },
          {
            id: "tr_scope_decision",
            session_id: "sess_9965",
            turn_id: "turn_user_1",
            stage: "scope_detection",
            event_type: "scope_decision",
            payload: {
              output: {
                feature_ids: [7],
                confidence: 0.82,
                reason: "日志命中支付特性",
              },
            },
            created_at: "2026-05-02T10:03:00",
            updated_at: "2026-05-02T10:03:00",
          },
          {
            id: "tr_sufficiency",
            session_id: "sess_9965",
            turn_id: "turn_user_1",
            stage: "sufficiency_judgement",
            event_type: "sufficiency_decision",
            payload: {
              output: {
                verdict: "insufficient",
                reason: "需要代码证据",
                next: "code_investigation",
              },
            },
            created_at: "2026-05-02T10:04:00",
            updated_at: "2026-05-02T10:04:00",
          },
          {
            id: "tr_wiki_scope",
            session_id: "sess_9965",
            turn_id: "turn_user_1",
            stage: "knowledge_retrieval",
            event_type: "wiki_scope_resolution",
            payload: {
              feature_id: 7,
              query: "请完整分析 GLM 调试链路。",
              defaults: [
                { node_id: 2, path: "知识库", label: "知识库" },
                { node_id: 3, path: "问题定位报告", label: "问题定位报告" },
              ],
              matches: [
                {
                  node_id: 11,
                  path: "知识库/调试链路",
                  label: "调试链路",
                  match_reason: "contains",
                  matched_phrase: "调试链路",
                },
              ],
            },
            created_at: "2026-05-02T10:04:10",
            updated_at: "2026-05-02T10:04:10",
          },
          {
            id: "tr_tool_result",
            session_id: "sess_9965",
            turn_id: "turn_user_1",
            stage: "code_investigation",
            event_type: "tool_result",
            payload: {
              id: "call_1",
              result: {
                ok: true,
                data: {
                  summary: "2 code matches for '启动失败'",
                  hits: [
                    {
                      path: "src/codeask/api/sessions.py",
                      line_number: 83,
                    },
                    {
                      path: "src/codeask/agent/runtime.py",
                      line_number: 42,
                    },
                  ],
                },
              },
            },
            created_at: "2026-05-02T10:04:30",
            updated_at: "2026-05-02T10:04:30",
          },
        ]);
      }
      const attachmentResponse = emptyAttachmentListResponse(input);
      if (attachmentResponse) {
        return attachmentResponse;
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "GLM 调试会话",
    );

    expect(
      await screen.findByText("请完整分析 GLM 调试链路。"),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "链路已经完成" }),
    ).toBeInTheDocument();
    expect(screen.getByText('const status = "ok";')).toBeInTheDocument();
    expect(screen.getByText("日志命中支付特性")).toBeInTheDocument();
    expect(screen.getByText("Wiki 范围：知识库、问题定位报告")).toBeInTheDocument();
    expect(screen.getByText(/需要代码证据/)).toBeInTheDocument();
    expect(screen.getByText("工具结果完成")).toBeInTheDocument();
    expect(
      screen.getByText(/2 code matches for '启动失败'/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/"ok":true/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /证据：支付接入说明 详情/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("这次回答是否解决问题？")).toBeInTheDocument();
    expect(scrollIntoView).not.toHaveBeenCalledWith(
      expect.objectContaining({ block: "end" }),
    );
    expect(container.querySelector(".message-meta")).not.toBeInTheDocument();
    expect(
      container.querySelector(".progress-stage-scroll"),
    ).not.toBeInTheDocument();
    expect(container.querySelector(".action-trace-scroll")).toBeInTheDocument();

    const copyMessageButton = screen.getByRole("button", {
      name: "复制 CodeAsk 消息",
    });
    fireEvent.click(copyMessageButton);
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        expect.stringContaining("建议补齐前端历史渲染"),
      ),
    );
    expect(
      await within(
        copyMessageButton.closest(".message-actions") as HTMLElement,
      ).findByText("已复制"),
    ).toBeInTheDocument();
    expect(screen.queryByText("已复制消息")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /工具结果完成/ }));
    const eventDialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(eventDialog).toBeInTheDocument();
    expect(
      within(eventDialog).getAllByText(/2 code matches for '启动失败'/).length,
    ).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /证据：支付接入说明/ }));
    const evidenceDialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(
      within(evidenceDialog).getByRole("link", { name: "知识库/支付接入说明" }),
    ).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=703&heading=%E6%94%AF%E4%BB%98%E6%8E%A5%E5%85%A5%E8%AF%B4%E6%98%8E+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4",
    );

    const copyCodeButton = screen.getByRole("button", { name: "复制代码块" });
    fireEvent.click(copyCodeButton);
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('const status = "ok";'),
    );
    expect(
      await within(
        copyCodeButton.closest(".markdown-code-block") as HTMLElement,
      ).findByText("已复制"),
    ).toBeInTheDocument();
    if (originalScrollIntoView) {
      Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
        configurable: true,
        value: originalScrollIntoView,
      });
    } else {
      Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });

  it("shows a visible error when deleting a session fails", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "线上启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/sessions/sess_1" && init?.method === "DELETE") {
          return new Response("", { status: 405 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(
      await within(sessionList).findByText("线上启动失败"),
    ).toBeInTheDocument();
    fireEvent.click(
      within(sessionList).getByRole("button", {
        name: "打开会话 线上启动失败 的更多操作",
      }),
    );
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "删除会话失败：API request failed with 405",
    );
    expect(within(sessionList).getByText("线上启动失败")).toBeInTheDocument();
  });

  it("shows a centered error dialog when preparing a session report fails", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (/^\/api\/sessions\/[^/]+\/turns$/.test(path)) {
          return jsonResponse([]);
        }
        if (/^\/api\/sessions\/[^/]+\/traces$/.test(path)) {
          return jsonResponse([]);
        }
        if (path === "/api/features") {
          return jsonResponse([feature]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return streamResponse("检查配置缺失。");
        }
        if (
          path === "/api/sessions/sess_1/reports/prepare" &&
          init?.method === "POST"
        ) {
          return new Response("", { status: 405 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "支付启动失败",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "生成报告失败：API request failed with 405",
    );
  });

  it("sends the selected session message and renders streamed progress", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "线上启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return streamResponse("检查配置缺失。");
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await within(screen.getByRole("region", { name: "会话列表" })).findByText(
        "线上启动失败",
      ),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "服务启动失败，日志显示配置缺失" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(
      await screen.findByText("服务启动失败，日志显示配置缺失"),
    ).toBeInTheDocument();
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();
    expect(screen.getByText("上下文已准备")).toBeInTheDocument();

    await waitFor(() => {
      const [, init] = fetchMock.mock.calls.find(([path]) =>
        String(path).includes("/messages"),
      ) as unknown as [string, RequestInit];
      expect(JSON.parse(String(init.body))).toMatchObject({
        content: "服务启动失败，日志显示配置缺失",
      });
      expect(JSON.parse(String(init.body))).not.toHaveProperty(
        "force_code_investigation",
      );
    });
  });

  it("switches messages and action trace while another session is streaming", async () => {
    let streamController: ReadableStreamDefaultController<Uint8Array> | null = null;
    const encoder = new TextEncoder();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "正在生成的会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: "sess_2",
              title: "历史会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T09:00:00",
              updated_at: "2026-04-30T09:00:00",
            },
          ]);
        }
        if (path === "/api/sessions/sess_1/turns") {
          return jsonResponse([]);
        }
        if (path === "/api/sessions/sess_1/traces") {
          return jsonResponse([]);
        }
        if (path === "/api/sessions/sess_2/turns") {
          return jsonResponse([
            {
              id: "turn_2_user",
              session_id: "sess_2",
              turn_index: 0,
              role: "user",
              content: "历史问题",
              evidence: null,
              created_at: "2026-04-30T09:00:00",
              updated_at: "2026-04-30T09:00:00",
            },
            {
              id: "turn_2_agent",
              session_id: "sess_2",
              turn_index: 1,
              role: "agent",
              content: "历史回答内容",
              evidence: null,
              created_at: "2026-04-30T09:00:01",
              updated_at: "2026-04-30T09:00:01",
            },
          ]);
        }
        if (path === "/api/sessions/sess_2/traces") {
          return jsonResponse([
            {
              id: "trace_2",
              session_id: "sess_2",
              turn_id: "turn_2_agent",
              stage: "chat_runtime",
              event_type: "tool_result",
              payload: {
                tool_name: "search_wiki",
                ok: true,
                summary: "历史轨迹命中 Wiki",
              },
              created_at: "2026-04-30T09:00:01",
              updated_at: "2026-04-30T09:00:01",
            },
          ]);
        }
        if (/^\/api\/sessions\/[^/]+\/attachments$/.test(path)) {
          return jsonResponse([]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return new Response(
            new ReadableStream({
              start(controller) {
                streamController = controller;
                controller.enqueue(
                  encoder.encode(
                    'event: text_delta\ndata: {"text":"生成中的回答"}\n\n',
                  ),
                );
              },
            }),
            {
              headers: {
                "Content-Type": "text/event-stream",
              },
            },
          );
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "正在生成的会话",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "开始生成" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("生成中的回答")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "历史会话" }));

    expect(
      await screen.findByRole("heading", { name: "历史会话" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("历史回答内容")).toBeInTheDocument();
    expect(await screen.findByText("历史轨迹命中 Wiki")).toBeInTheDocument();
    expect(screen.queryByText("生成中的回答")).not.toBeInTheDocument();

    await act(async () => {
      streamController?.enqueue(
        encoder.encode('event: text_delta\ndata: {"text":"继续输出"}\n\n'),
      );
    });
    fireEvent.click(screen.getByRole("button", { name: "正在生成的会话" }));
    expect(
      await screen.findByRole("heading", { name: "正在生成的会话" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("生成中的回答继续输出")).toBeInTheDocument();
    expect(screen.queryByText("历史回答内容")).not.toBeInTheDocument();

    await act(async () => {
      streamController?.enqueue(
        encoder.encode('event: done\ndata: {"turn_id":"turn_stream"}\n\n'),
      );
      streamController?.close();
    });
  });

  it("keeps previous action trace entries when sending a follow-up message", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/sessions/sess_1/turns") {
          return jsonResponse([]);
        }
        if (path === "/api/sessions/sess_1/traces") {
          return jsonResponse([
            {
              id: "trace_previous",
              session_id: "sess_1",
              turn_id: "turn_previous",
              stage: "chat_runtime",
              event_type: "tool_result",
              payload: {
                tool_name: "search_wiki",
                ok: true,
                summary: "命中小米病历",
              },
              created_at: "2026-05-02T10:00:00",
              updated_at: "2026-05-02T10:00:00",
            },
          ]);
        }
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "小米病情会话",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-05-02T10:00:00",
              updated_at: "2026-05-02T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          const encoder = new TextEncoder();
          return new Response(
            new ReadableStream({
              start(controller) {
                controller.enqueue(
                  encoder.encode(
                    'event: tool_call\ndata: {"tool_call_id":"call_follow","tool_name":"search_code","arguments_summary":{"query":"buddy"}}\n\n',
                  ),
                );
                controller.enqueue(
                  encoder.encode(
                    'event: done\ndata: {"turn_id":"turn_follow"}\n\n',
                  ),
                );
                controller.close();
              },
            }),
            {
              headers: {
                "Content-Type": "text/event-stream",
                "X-CodeAsk-Turn-Id": "turn_interrupted",
              },
            },
          );
        }
        if (
          path === "/api/sessions/sess_1/turns/turn_interrupted/abort" &&
          init?.method === "POST"
        ) {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "小米病情会话",
    );
    expect(await screen.findByText("命中小米病历")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "再查一下相关代码" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("准备使用 代码搜索")).toBeInTheDocument();
    expect(screen.getByText("命中小米病历")).toBeInTheDocument();
  });

  it("groups persisted action trace entries by conversation turn", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/sessions/sess_1/turns") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_1/traces") {
        return jsonResponse([
          {
            id: "trace_turn_1",
            session_id: "sess_1",
            turn_id: "turn_1",
            stage: "chat_runtime",
            event_type: "retrieval_context",
            payload: {
              feature_candidates: [],
              wiki_hits: [],
              report_hits: [],
            },
            created_at: "2026-05-02T10:00:00",
            updated_at: "2026-05-02T10:00:00",
          },
          {
            id: "trace_turn_2",
            session_id: "sess_1",
            turn_id: "turn_2",
            stage: "chat_runtime",
            event_type: "tool_result",
            payload: {
              tool_name: "search_code",
              ok: true,
              summary: "命中 3 个代码位置",
            },
            created_at: "2026-05-02T10:01:00",
            updated_at: "2026-05-02T10:01:00",
          },
        ]);
      }
      const attachmentResponse = emptyAttachmentListResponse(input, init);
      if (attachmentResponse) {
        return attachmentResponse;
      }
      if (path === "/api/sessions") {
        return jsonResponse([
          {
            id: "sess_1",
            title: "多轮追踪",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-05-02T10:00:00",
            updated_at: "2026-05-02T10:00:00",
          },
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "多轮追踪",
    );

    expect(await screen.findByText("第 1 轮")).toBeInTheDocument();
    expect(screen.getByText("第 2 轮")).toBeInTheDocument();
    expect(screen.getByText("上下文已准备")).toBeInTheDocument();
    expect(screen.getByText("代码搜索完成")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /代码搜索完成/ }));
    const details = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(within(details).getByText("工具名称")).toBeInTheDocument();
    expect(within(details).getByText("search_code")).toBeInTheDocument();
    expect(within(details).getByText("所属轮次")).toBeInTheDocument();
    expect(within(details).getByText("turn_2")).toBeInTheDocument();
    expect(within(details).getByText("发生时间")).toBeInTheDocument();
    expect(within(details).getByText("2026-05-02T10:01:00")).toBeInTheDocument();
    expect(within(details).getByText("结果摘要")).toBeInTheDocument();
    expect(within(details).getAllByText("命中 3 个代码位置").length).toBeGreaterThan(0);
  });

  it("sends with Enter and inserts newlines with Shift+Enter or Ctrl+Enter", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "快捷键测试",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-05-02T10:00:00",
              updated_at: "2026-05-02T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return streamResponse("收到。");
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "快捷键测试",
    );
    const input = screen.getByLabelText("会话输入") as HTMLTextAreaElement;

    fireEvent.change(input, { target: { value: "第一行" } });
    input.setSelectionRange(2, 2);
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(input.value).toBe("第一\n行");

    input.setSelectionRange(input.value.length, input.value.length);
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
    expect(input.value).toBe("第一\n行\n");
    expect(
      fetchMock.mock.calls.some(
        ([path, options]) =>
          path === "/api/sessions/sess_1/messages" &&
          (options as RequestInit | undefined)?.method === "POST",
      ),
    ).toBe(false);

    fireEvent.change(input, { target: { value: "直接发送" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/sess_1/messages",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("stops an active generation and rolls back the local turn", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "中断测试",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-05-02T10:00:00",
              updated_at: "2026-05-02T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          const payload = JSON.parse(String(init.body)) as {
            client_turn_id?: string;
          };
          expect(payload.client_turn_id).toMatch(/^turn_client_/);
          const encoder = new TextEncoder();
          return new Response(
            new ReadableStream({
              start(controller) {
                controller.enqueue(
                  encoder.encode(
                    'event: retrieval_context\ndata: {"feature_candidates":[],"wiki_hits":[],"report_hits":[]}\n\n',
                  ),
                );
                controller.enqueue(
                  encoder.encode('event: text_delta\ndata: {"text":"正在分析"}\n\n'),
                );
                init?.signal?.addEventListener("abort", () => {
                  controller.error(new DOMException("Aborted", "AbortError"));
                });
              },
            }),
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        if (
          /^\/api\/sessions\/sess_1\/turns\/turn_client_[^/]+\/abort$/.test(
            path,
          ) &&
          init?.method === "POST"
        ) {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "中断测试",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "需要中断的长任务" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("正在分析")).toBeInTheDocument();
    expect(screen.getByText("上下文已准备")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "停止" }));

    await waitFor(() => {
      expect(screen.queryByText("需要中断的长任务")).not.toBeInTheDocument();
      expect(screen.queryByText("正在分析")).not.toBeInTheDocument();
      expect(screen.queryByText("上下文已准备")).not.toBeInTheDocument();
    });
    expect(
      fetchMock.mock.calls.some(
        ([path, options]) =>
          /^\/api\/sessions\/sess_1\/turns\/turn_client_[^/]+\/abort$/.test(
            String(path),
          ) && (options as RequestInit | undefined)?.method === "POST",
      ),
    ).toBe(true);
    expect(await screen.findByText("已停止生成")).toBeInTheDocument();
  });

  it("renders runtime transparency events and ask-user prompts in the session workspace", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return transparencyStreamResponse();
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await within(screen.getByRole("region", { name: "会话列表" })).findByText(
        "支付启动失败",
      ),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("日志命中支付特性")).toBeInTheDocument();
    expect(screen.getByText("评估证据")).toBeInTheDocument();
    expect(screen.getByText("准备使用 Wiki 搜索")).toBeInTheDocument();
    expect(screen.getByText("Wiki 搜索完成")).toBeInTheDocument();
    expect(screen.getByText("证据：启动手册")).toBeInTheDocument();
    expect(screen.getByText("请补充完整启动日志")).toBeInTheDocument();
    expect(
      await screen.findByText("需要补充：请补充完整启动日志"),
    ).toBeInTheDocument();
  });

  it("shows a visible notice when the runtime stream emits an error", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "运行错误",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return new Response(
            'event: error\ndata: {"message":"模型上下文超限"}\n\n',
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "运行错误",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "触发错误" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("模型上下文超限")).toBeInTheDocument();
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "Agent 运行失败：模型上下文超限",
    );
  });

  it("submits feedback and telemetry from the session workspace", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "支付启动失败",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/messages" &&
          init?.method === "POST"
        ) {
          return new Response(
            [
              'event: text_delta\ndata: {"text":"检查配置缺失。"}',
              'event: done\ndata: {"turn_id":"turn_stream"}',
            ].join("\n\n"),
            { headers: { "Content-Type": "text/event-stream" } },
          );
        }
        if (path === "/api/events" && init?.method === "POST") {
          return jsonResponse({ ok: true, id: "ev_1" }, 201);
        }
        if (path === "/api/feedback" && init?.method === "POST") {
          return jsonResponse({ ok: true }, 201);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText(
      "支付启动失败",
    );
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "已解决" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/events",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/feedback",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("已反馈 · 已解决")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([path, options]) =>
          String(path) === "/api/feedback" &&
          JSON.parse(String((options as RequestInit).body)).session_turn_id ===
            "turn_stream",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([path, options]) =>
          String(path) === "/api/events" &&
          JSON.parse(String((options as RequestInit).body)).event_type ===
            "force_deeper_investigation",
      ),
    ).toBe(false);
  });

  it("creates a default session when uploading a log before any session exists", async () => {
    let uploadedAttachment = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (
          /^\/api\/sessions\/[^/]+\/turns$/.test(path) &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([]);
        }
        if (
          /^\/api\/sessions\/[^/]+\/traces$/.test(path) &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([]);
        }
        if (
          path === "/api/sessions/sess_new/attachments" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse(
            uploadedAttachment
              ? [
                  {
                    id: "att_1",
                    session_id: "sess_new",
                    kind: "log",
                    display_name: "app.log",
                    original_filename: "app.log",
                    file_path: "/tmp/sessions/sess_new/att_1.log",
                    mime_type: "text/plain",
                    size_bytes: 5,
                    created_at: "2026-04-30T10:00:00",
                    updated_at: "2026-04-30T10:00:00",
                  },
                ]
              : [],
          );
        }
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (
          path === "/api/sessions" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([]);
        }
        if (path === "/api/sessions" && init?.method === "POST") {
          return jsonResponse(
            {
              id: "sess_new",
              title: "app.log",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        if (
          path === "/api/sessions/sess_new/attachments" &&
          init?.method === "POST"
        ) {
          uploadedAttachment = true;
          return jsonResponse(
            {
              id: "att_1",
              session_id: "sess_new",
              kind: "log",
              display_name: "app.log",
              original_filename: "app.log",
              file_path: "/tmp/sessions/sess_new/att_1.log",
              mime_type: "text/plain",
              size_bytes: 5,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const fileInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    expect(fileInput).toBeTruthy();
    fireEvent.change(fileInput, {
      target: {
        files: [new File(["ERROR"], "app.log", { type: "text/plain" })],
      },
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/sess_new/attachments",
        expect.objectContaining({ method: "POST" }),
      );
    });
    const attachmentPanel = await screen.findByRole("region", {
      name: "会话数据",
    });
    expect(attachmentPanel).toBeInTheDocument();
    expect(
      await within(attachmentPanel).findByText("app.log"),
    ).toBeInTheDocument();
  });

  it("shows a dialog instead of opening the file picker when session attachments are disabled", async () => {
    const inputClick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(() => undefined);
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (
          path === "/api/sessions" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([]);
        }
        if (path === "/api/system-settings") {
          return jsonResponse({ session_attachments_enabled: false });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(<App />);

      fireEvent.click(await screen.findByRole("button", { name: "上传日志" }));

      expect(inputClick).not.toHaveBeenCalled();
      expect(
        await screen.findByRole("alertdialog", { name: "操作失败" }),
      ).toBeInTheDocument();
      expect(screen.getByText("该功能已被禁用")).toBeInTheDocument();
      expect(fetchMock).not.toHaveBeenCalledWith(
        expect.stringMatching(/\/attachments$/),
        expect.objectContaining({ method: "POST" }),
      );
    } finally {
      inputClick.mockRestore();
      queryClient.removeQueries({ queryKey: ["system-settings"] });
    }
  });

  it("clears a stale disabled upload status when attachments are enabled again", async () => {
    const inputClick = vi
      .spyOn(HTMLInputElement.prototype, "click")
      .mockImplementation(() => undefined);
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (
          path === "/api/sessions" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([
            {
              id: "sess_upload",
              title: "上传测试",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              title_source: "manual",
              title_generated_at: null,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (path === "/api/system-settings") {
          return jsonResponse({ session_attachments_enabled: true });
        }
        if (
          path === "/api/sessions/sess_upload/attachments" &&
          init?.method === "POST"
        ) {
          return jsonResponse({ detail: "该功能已被禁用" }, 403);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      render(<App />);
      expect(
        await screen.findByRole("heading", { name: "上传测试" }),
      ).toBeInTheDocument();

      const fileInput = document.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement;
      expect(fileInput).toBeTruthy();
      fireEvent.change(fileInput, {
        target: {
          files: [new File(["ERROR"], "app.log", { type: "text/plain" })],
        },
      });

      expect(
        await screen.findByText("上传日志失败：该功能已被禁用"),
      ).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "知道了" }));
      expect(screen.queryByText("该功能已被禁用")).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "上传日志" }));

      await waitFor(() => expect(inputClick).toHaveBeenCalledTimes(1));
      expect(screen.queryByText("该功能已被禁用")).not.toBeInTheDocument();
    } finally {
      inputClick.mockRestore();
      queryClient.removeQueries({ queryKey: ["system-settings"] });
    }
  });

  it("shows a compact session id pill and lets users copy the full id", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_lookup_1",
              title: "定位存储目录",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "定位存储目录" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Session ID")).not.toBeInTheDocument();
    expect(screen.getByText("sess_look")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "复制完整会话 ID sess_lookup_1" }),
    );

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("sess_lookup_1"),
    );
    expect(await screen.findByText("复制成功")).toBeInTheDocument();
    await waitFor(
      () => expect(screen.queryByText("复制成功")).not.toBeInTheDocument(),
      {
        timeout: 1400,
      },
    );
  });

  it("keeps attachments scoped to the selected session and supports rename and delete actions", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (
          path === "/api/sessions/sess_1/attachments" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([
            {
              id: "att_a",
              session_id: "sess_1",
              kind: "log",
              display_name: "service.log",
              original_filename: "service.log",
              file_path: "/tmp/sessions/sess_1/att_a.log",
              mime_type: "text/plain",
              size_bytes: 12,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_2/attachments" &&
          (!init?.method || init.method === "GET")
        ) {
          return jsonResponse([
            {
              id: "att_b",
              session_id: "sess_2",
              kind: "log",
              display_name: "service.log",
              original_filename: "service.log",
              file_path: "/tmp/sessions/sess_2/att_b.log",
              mime_type: "text/plain",
              size_bytes: 13,
              created_at: "2026-04-30T11:00:00",
              updated_at: "2026-04-30T11:00:00",
            },
          ]);
        }
        const attachmentResponse = emptyAttachmentListResponse(input, init);
        if (attachmentResponse) {
          return attachmentResponse;
        }
        if (path === "/api/sessions") {
          return jsonResponse([
            {
              id: "sess_1",
              title: "节点 A",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T10:00:00",
              updated_at: "2026-04-30T10:00:00",
            },
            {
              id: "sess_2",
              title: "节点 B",
              created_by_subject_id: "client_test",
              status: "active",
              pinned: false,
              created_at: "2026-04-30T11:00:00",
              updated_at: "2026-04-30T11:00:00",
            },
          ]);
        }
        if (
          path === "/api/sessions/sess_1/attachments/att_a" &&
          init?.method === "PATCH"
        ) {
          return jsonResponse({
            id: "att_a",
            session_id: "sess_1",
            kind: "log",
            display_name: "node-a.log",
            original_filename: "service.log",
            file_path: "/tmp/sessions/sess_1/att_a.log",
            mime_type: "text/plain",
            size_bytes: 12,
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:30:00",
          });
        }
        if (
          path === "/api/sessions/sess_1/attachments/att_a" &&
          init?.method === "DELETE"
        ) {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal(
      "prompt",
      vi.fn(() => "node-a.log"),
    );
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true),
    );

    render(<App />);

    const sessionList = await screen.findByRole("region", { name: "会话列表" });
    fireEvent.click(
      await within(sessionList).findByRole("button", { name: "节点 A" }),
    );
    const attachmentPanel = await screen.findByRole("region", {
      name: "会话数据",
    });
    expect(
      within(attachmentPanel).getByText("service.log"),
    ).toBeInTheDocument();

    fireEvent.click(
      within(attachmentPanel).getByRole("button", {
        name: "重命名 service.log",
      }),
    );
    expect(await screen.findByText("node-a.log")).toBeInTheDocument();
    expect(
      await screen.findByText("已重命名为 node-a.log"),
    ).toBeInTheDocument();
    await waitFor(
      () =>
        expect(
          screen.queryByText("已重命名为 node-a.log"),
        ).not.toBeInTheDocument(),
      {
        timeout: 3600,
      },
    );
    fireEvent.click(
      within(attachmentPanel).getByRole("button", { name: "删除 node-a.log" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/sess_1/attachments/att_a",
        expect.objectContaining({ method: "DELETE" }),
      );
    });

    fireEvent.click(
      within(sessionList).getByRole("button", { name: "节点 B" }),
    );
    expect(await screen.findByText("service.log")).toBeInTheDocument();
    expect(screen.queryByText("node-a.log")).not.toBeInTheDocument();
  });
});
