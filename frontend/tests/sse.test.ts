import { describe, expect, it, vi } from "vitest";

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
      }
    }),
    {
      headers: {
        "Content-Type": "text/event-stream"
      }
    }
  );
}

describe("session SSE client", () => {
  it("posts a message with identity headers and parses named agent events", async () => {
    const fetchMock = vi.fn(async () =>
      sseResponse([
        'event: stage_transition\ndata: {"stage":"knowledge_retrieval"}\n\n',
        'event: text_delta\ndata: {"text":"需要检查"}\n\n',
        'event: done\ndata: {}\n\n'
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const events: AgentEvent[] = [];
    await streamSessionMessage({
      sessionId: "sess_1",
      content: "为什么启动失败",
      force_code_investigation: true,
      onEvent: (event) => events.push(event)
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/sessions/sess_1/messages");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-Subject-Id")).toMatch(/^client_/);
    expect(JSON.parse(String(init.body))).toMatchObject({
      content: "为什么启动失败",
      force_code_investigation: true,
      feature_ids: [],
      repo_bindings: []
    });
    expect(events).toEqual([
      { type: "stage_transition", data: { stage: "knowledge_retrieval" } },
      { type: "text_delta", data: { text: "需要检查" } },
      { type: "done", data: {} }
    ]);
  });
});
