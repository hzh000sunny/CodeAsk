import { beforeEach, describe, expect, it, vi } from "vitest";

import { setGuestLlmConfig } from "../src/lib/identity";
import { streamSessionMessage } from "../src/lib/sse";
import type { AgentEvent } from "../src/types/sse";

function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder();
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

describe("session SSE client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("posts a message with identity headers and parses named agent events", async () => {
    const fetchMock = vi.fn(async () =>
      sseResponse([
        'event: stage_transition\ndata: {"stage":"knowledge_retrieval"}\n\n',
        'event: text_delta\ndata: {"text":"需要检查"}\n\n',
        "event: done\ndata: {}\n\n",
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events: AgentEvent[] = [];
    await streamSessionMessage({
      sessionId: "sess_1",
      content: "为什么启动失败",
      onEvent: (event) => events.push(event),
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(path).toBe("/api/sessions/sess_1/messages");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-Subject-Id")).toMatch(/^client_/);
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "为什么启动失败",
      feature_ids: [],
      repo_bindings: [],
    });
    expect(JSON.parse(String(init.body))).not.toHaveProperty(
      "force_code_investigation",
    );
    expect(JSON.parse(String(init.body))).not.toHaveProperty("guest_llm_config");
    expect(events).toEqual([
      { type: "stage_transition", data: { stage: "knowledge_retrieval" } },
      { type: "text_delta", data: { text: "需要检查" } },
      { type: "done", data: {} },
    ]);
  });

  it("includes browser-local guest LLM config in the message request body", async () => {
    setGuestLlmConfig({
      name: "访客模型",
      mode: "custom",
      provider_id: "guest-gateway",
      base_url: "http://guest.llm/v1",
      api_key: "sk-guest",
      headers: { Authorization: "Bearer sk-guest" },
      model_name: "guest-model",
      reasoning_profile: "custom_json",
      reasoning_profile_json: '{"thinking":true}',
    });
    const fetchMock = vi.fn(
      async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode("event: done\ndata: {}\n\n"));
              controller.close();
            },
          }),
          { status: 200 },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await streamSessionMessage({
      sessionId: "sess_guest",
      content: "你好",
      onEvent: () => undefined,
    });

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "你好",
      guest_llm_config: {
        mode: "custom",
        provider_id: "guest-gateway",
        base_url: "http://guest.llm/v1",
        api_key: "sk-guest",
        headers: { Authorization: "Bearer sk-guest" },
        model_name: "guest-model",
        reasoning_profile: "custom_json",
        reasoning_profile_json: '{"thinking":true}',
      },
    });
  });
});
