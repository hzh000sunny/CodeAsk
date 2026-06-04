import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageStream } from "../src/components/session/MessageStream";
import type { ActionTraceEvent } from "../src/components/session/action-trace/action-trace-model";

describe("MessageStream", () => {
  it("preserves line breaks in user message bubbles", () => {
    const { container } = render(
      <MessageStream
        messages={[
          {
            id: "msg_user_multiline",
            role: "user",
            content: "第一行\n第二行",
          },
        ]}
      />,
    );

    const message = container.querySelector(".plain-message-content");
    expect(message?.textContent).toBe("第一行\n第二行");
    expect(message).toHaveClass("plain-message-content");
  });

  it("marks stopped assistant messages and explains empty stopped output", () => {
    render(
      <MessageStream
        messages={[
          {
            id: "msg_stopped",
            role: "assistant",
            content: "",
            status: "done",
            stoppedAt: "2026-05-28T10:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByText("已停止")).toBeInTheDocument();
    expect(screen.getByText("用户在模型回复前停止了这一轮")).toBeInTheDocument();
  });

  it("renders an inviting empty state before any message", () => {
    render(<MessageStream messages={[]} />);
    expect(screen.getByText("开始一次代码调查")).toBeInTheDocument();
  });

  it("gives the assistant a speaker gutter and a blinking caret while streaming", () => {
    const { container } = render(
      <MessageStream
        messages={[
          { id: "msg_user_1", role: "user", content: "为什么会 401？" },
          {
            id: "msg_assistant_1",
            role: "assistant",
            content: "正在排查……",
            status: "streaming",
          },
        ]}
      />,
    );

    expect(screen.getByText("CodeAsk")).toBeInTheDocument();
    expect(container.querySelector(".turn-avatar")?.textContent).toBe("CA");
    expect(container.querySelector(".stream-caret")).toBeInTheDocument();
  });

  it("threads live action-trace steps inline under the streaming turn", () => {
    const insights: ActionTraceEvent[] = [
      {
        id: "tool_call_live",
        kind: "tool_call",
        title: "准备使用 代码搜索",
        detail: "query=token_expiry",
        status: "running",
        turnId: "live_msg_assistant_1",
      },
    ];

    render(
      <MessageStream
        insights={insights}
        messages={[
          { id: "msg_user_1", role: "user", content: "为什么会 401？" },
          {
            id: "msg_assistant_1",
            role: "assistant",
            content: "",
            status: "streaming",
          },
        ]}
      />,
    );

    // Live turn timeline is expanded, so the step is visible inline.
    expect(screen.getByText("准备使用 代码搜索")).toBeInTheDocument();
    expect(screen.getByText("调查进行中")).toBeInTheDocument();
  });

  it("joins reloaded history traces by the preceding user turn id", () => {
    // Persisted agent turns carry their own id while traces are keyed by the
    // user turn id, so the inline timeline must join on the preceding user
    // message. A finished turn is collapsed, so the timeline summary (not the
    // step list) proves the join succeeded.
    const insights: ActionTraceEvent[] = [
      {
        id: "trace_1",
        kind: "retrieval",
        title: "已准备 5 条上下文",
        detail: "5 条 Wiki",
        status: "info",
        turnId: "turn_user_42",
      },
    ];

    render(
      <MessageStream
        insights={insights}
        messages={[
          { id: "turn_user_42", role: "user", content: "历史问题" },
          {
            id: "turn_agent_99",
            role: "assistant",
            content: "历史回答",
            status: "done",
            turnId: "turn_agent_99",
          },
        ]}
      />,
    );

    expect(screen.getByRole("button", { name: /调查过程/ })).toBeInTheDocument();
  });
});
