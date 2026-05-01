import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function streamResponse(text: string) {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            `event: stage_transition\ndata: {"stage":"knowledge_retrieval","label":"知识检索"}\n\n`
          )
        );
        controller.enqueue(encoder.encode(`event: text_delta\ndata: {"text":"${text}"}\n\n`));
        controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
        controller.close();
      }
    }),
    {
      headers: {
        "Content-Type": "text/event-stream"
      }
    }
  );
}

function transparencyStreamResponse() {
  const encoder = new TextEncoder();
  const chunks = [
    'event: scope_detection\ndata: {"feature_ids":[7,9],"confidence":0.82,"reason":"日志命中支付特性"}\n\n',
    'event: sufficiency_judgement\ndata: {"verdict":"insufficient","reason":"缺少启动参数","next":"code_investigation"}\n\n',
    'event: tool_call\ndata: {"id":"call_1","name":"search_documents","arguments":{"q":"启动失败"}}\n\n',
    'event: tool_result\ndata: {"id":"call_1","result":{"ok":true,"hits":2}}\n\n',
    'event: evidence\ndata: {"item":{"id":"ev_1","source":"wiki","title":"启动手册","locator":"docs/start.md"}}\n\n',
    'event: ask_user\ndata: {"ask_id":"ask_1","question":"请补充完整启动日志","options":["上传日志"],"reason":"当前证据不足"}\n\n'
  ];
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) {
          controller.enqueue(encoder.encode(chunk));
        }
        controller.close();
      }
    }),
    {
      headers: {
        "Content-Type": "text/event-stream"
      }
    }
  );
}

function emptyAttachmentListResponse(input: RequestInfo | URL, init?: RequestInit) {
  const path = String(input);
  if (/^\/api\/sessions\/[^/]+\/attachments$/.test(path) && (!init?.method || init.method === "GET")) {
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
  updated_at: "2026-04-30T10:00:00"
};

describe("SessionWorkspace streaming interaction", () => {
  it("deletes a session from the session list", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          },
          {
            id: "sess_2",
            title: "支付回调超时",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T09:00:00",
            updated_at: "2026-04-30T09:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_1" && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(await within(sessionList).findByText("线上启动失败")).toBeInTheDocument();
    fireEvent.click(within(sessionList).getByRole("button", { name: "打开会话 线上启动失败 的更多操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));

    expect(screen.getByRole("dialog", { name: "删除会话" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/sessions/sess_1",
      expect.objectContaining({ method: "DELETE" })
    );
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(within(sessionList).queryByText("线上启动失败")).not.toBeInTheDocument());
    expect(within(sessionList).getByText("支付回调超时")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sessions/sess_1",
      expect.objectContaining({ method: "DELETE" })
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(await within(sessionList).findByText("线上启动失败")).toBeInTheDocument();
    fireEvent.click(within(sessionList).getByRole("button", { name: "打开会话 线上启动失败 的更多操作" }));

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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText("线上启动失败");
    const composer = screen.getByRole("region", { name: "会话输入操作区" });
    expect(within(composer).getByRole("button", { name: "生成报告" })).toBeInTheDocument();
    const header = document.querySelector(".page-header") as HTMLElement;
    expect(within(header).queryByRole("button", { name: "生成报告" })).not.toBeInTheDocument();

    const actionLabels = Array.from(composer.querySelectorAll("label,button")).map((node) =>
      node.textContent?.trim()
    );
    expect(actionLabels.indexOf("强制代码调查")).toBeLessThan(actionLabels.indexOf("生成报告"));
    expect(actionLabels.indexOf("生成报告")).toBeLessThan(actionLabels.indexOf("发送"));
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/features") {
        return jsonResponse([feature]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText("线上启动失败");
    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));

    expect(screen.getByRole("dialog", { name: "暂不能生成报告" })).toBeInTheDocument();
    expect(screen.getByText(/至少完成一次问答/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/sessions/sess_1/reports",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("confirms report generation with a feature and links to the generated report", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/features") {
        return jsonResponse([feature]);
      }
      if (path === "/api/sessions/sess_1/messages" && init?.method === "POST") {
        return new Response(
          [
            'event: scope_detection\ndata: {"feature_ids":[7],"confidence":0.91,"reason":"命中支付特性"}',
            'event: text_delta\ndata: {"text":"检查配置缺失。"}',
            'event: done\ndata: {}'
          ].join("\n\n"),
          { headers: { "Content-Type": "text/event-stream" } }
        );
      }
      if (path === "/api/sessions/sess_1/reports" && init?.method === "POST") {
        return jsonResponse({
          id: 42,
          feature_id: 7,
          title: "支付启动失败定位报告",
          body_markdown: "# 支付启动失败定位报告",
          metadata_json: { source: "session", session_id: "sess_1" },
          status: "draft",
          verified: false,
          verified_by: null,
          verified_at: null,
          created_by_subject_id: "client_test",
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00"
        }, 201);
      }
      if (path === "/api/documents?feature_id=7") {
        return jsonResponse([]);
      }
      if (path === "/api/reports?feature_id=7") {
        return jsonResponse([
          {
            id: 42,
            feature_id: 7,
            title: "支付启动失败定位报告",
            body_markdown: "# 支付启动失败定位报告",
            metadata_json: { source: "session", session_id: "sess_1" },
            status: "draft",
            verified: false,
            verified_by: null,
            verified_at: null,
            created_by_subject_id: "client_test",
            created_at: "2026-04-30T10:00:00",
            updated_at: "2026-04-30T10:00:00"
          }
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
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await within(screen.getByRole("region", { name: "会话列表" })).findByText("支付启动失败");
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" }
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "生成报告" }));
    expect(screen.getByRole("dialog", { name: "生成问题定位报告" })).toBeInTheDocument();
    expect(screen.getByLabelText("绑定特性")).toHaveValue("7");
    fireEvent.click(screen.getByRole("button", { name: "确认生成" }));

    await waitFor(() => {
      const [, init] = fetchMock.mock.calls.find(([path, options]) =>
        path === "/api/sessions/sess_1/reports" && (options as RequestInit | undefined)?.method === "POST"
      ) as unknown as [string, RequestInit];
      expect(JSON.parse(String(init.body))).toMatchObject({
        feature_id: 7,
        title: "支付启动失败定位报告"
      });
    });
    expect(await screen.findByRole("dialog", { name: "报告已生成" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "查看报告" }));

    expect(await screen.findByRole("tab", { name: "问题报告", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "支付启动失败定位报告" })).toBeInTheDocument();
  });

  it("shows a visible error when deleting a session fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_1" && init?.method === "DELETE") {
        return jsonResponse({ detail: "Method Not Allowed" }, 405);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const sessionList = screen.getByRole("region", { name: "会话列表" });
    expect(await within(sessionList).findByText("线上启动失败")).toBeInTheDocument();
    fireEvent.click(within(sessionList).getByRole("button", { name: "打开会话 线上启动失败 的更多操作" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "删除" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("删除会话失败");
    expect(within(sessionList).getByText("线上启动失败")).toBeInTheDocument();
  });

  it("sends the selected session message and renders streamed progress", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_1/messages" && init?.method === "POST") {
        return streamResponse("检查配置缺失。");
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await within(screen.getByRole("region", { name: "会话列表" })).findByText("线上启动失败")
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "服务启动失败，日志显示配置缺失" }
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("服务启动失败，日志显示配置缺失")).toBeInTheDocument();
    expect(await screen.findByText("检查配置缺失。")).toBeInTheDocument();
    expect(screen.getByText("知识检索")).toBeInTheDocument();

    await waitFor(() => {
      const [, init] = fetchMock.mock.calls.find(([path]) =>
        String(path).includes("/messages")
      ) as unknown as [string, RequestInit];
      expect(JSON.parse(String(init.body))).toMatchObject({
        content: "服务启动失败，日志显示配置缺失",
        force_code_investigation: false
      });
    });
  });

  it("renders runtime transparency events and ask-user prompts in the session workspace", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_1/messages" && init?.method === "POST") {
        return transparencyStreamResponse();
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(
      await within(screen.getByRole("region", { name: "会话列表" })).findByText("支付启动失败")
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("会话输入"), {
      target: { value: "支付服务启动失败" }
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("日志命中支付特性")).toBeInTheDocument();
    expect(screen.getByText("insufficient")).toBeInTheDocument();
    expect(screen.getByText(/search_documents/)).toBeInTheDocument();
    expect(screen.getByText(/启动手册/)).toBeInTheDocument();
    expect(screen.getByText("请补充完整启动日志")).toBeInTheDocument();
    expect(await screen.findByText("需要补充：请补充完整启动日志")).toBeInTheDocument();
  });

  it("creates a default session when uploading a log before any session exists", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
          authenticated: false
        });
      }
      if (path === "/api/features") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions" && (!init?.method || init.method === "GET")) {
        return jsonResponse([]);
      }
      if (path === "/api/sessions" && init?.method === "POST") {
        return jsonResponse({
          id: "sess_new",
          title: "app.log",
          created_by_subject_id: "client_test",
          status: "active",
          pinned: false,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00"
        }, 201);
      }
      if (path === "/api/sessions/sess_new/attachments" && init?.method === "POST") {
        return jsonResponse({
          id: "att_1",
          session_id: "sess_new",
          kind: "log",
          display_name: "app.log",
          original_filename: "app.log",
          file_path: "/tmp/sessions/sess_new/att_1.log",
          mime_type: "text/plain",
          size_bytes: 5,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00"
        }, 201);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();
    fireEvent.change(fileInput, {
      target: {
        files: [new File(["ERROR"], "app.log", { type: "text/plain" })]
      }
    });

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/sess_new/attachments",
        expect.objectContaining({ method: "POST" })
      );
    });
    const attachmentPanel = await screen.findByRole("region", { name: "会话数据" });
    expect(attachmentPanel).toBeInTheDocument();
    expect(await within(attachmentPanel).findByText("app.log")).toBeInTheDocument();
  });

  it("shows a compact session id pill and lets users copy the full id", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText }
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "定位存储目录" })).toBeInTheDocument();
    expect(screen.queryByText("Session ID")).not.toBeInTheDocument();
    expect(screen.getByText("sess_look")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制完整会话 ID sess_lookup_1" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("sess_lookup_1"));
    expect(await screen.findByText("复制成功")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("复制成功")).not.toBeInTheDocument(), {
      timeout: 1400
    });
  });

  it("keeps attachments scoped to the selected session and supports rename and delete actions", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/sessions/sess_1/attachments" && (!init?.method || init.method === "GET")) {
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
            updated_at: "2026-04-30T10:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_2/attachments" && (!init?.method || init.method === "GET")) {
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
            updated_at: "2026-04-30T11:00:00"
          }
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
            updated_at: "2026-04-30T10:00:00"
          },
          {
            id: "sess_2",
            title: "节点 B",
            created_by_subject_id: "client_test",
            status: "active",
            pinned: false,
            created_at: "2026-04-30T11:00:00",
            updated_at: "2026-04-30T11:00:00"
          }
        ]);
      }
      if (path === "/api/sessions/sess_1/attachments/att_a" && init?.method === "PATCH") {
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
          updated_at: "2026-04-30T10:30:00"
        });
      }
      if (path === "/api/sessions/sess_1/attachments/att_a" && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("prompt", vi.fn(() => "node-a.log"));
    vi.stubGlobal("confirm", vi.fn(() => true));

    render(<App />);

    const sessionList = await screen.findByRole("region", { name: "会话列表" });
    fireEvent.click(await within(sessionList).findByRole("button", { name: "节点 A" }));
    const attachmentPanel = await screen.findByRole("region", { name: "会话数据" });
    expect(within(attachmentPanel).getByText("service.log")).toBeInTheDocument();

    fireEvent.click(within(attachmentPanel).getByRole("button", { name: "重命名 service.log" }));
    expect(await screen.findByText("node-a.log")).toBeInTheDocument();
    expect(await screen.findByText("已重命名为 node-a.log")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("已重命名为 node-a.log")).not.toBeInTheDocument(), {
      timeout: 3600
    });
    fireEvent.click(within(attachmentPanel).getByRole("button", { name: "删除 node-a.log" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sessions/sess_1/attachments/att_a",
        expect.objectContaining({ method: "DELETE" })
      );
    });

    fireEvent.click(within(sessionList).getByRole("button", { name: "节点 B" }));
    expect(await screen.findByText("service.log")).toBeInTheDocument();
    expect(screen.queryByText("node-a.log")).not.toBeInTheDocument();
  });
});
