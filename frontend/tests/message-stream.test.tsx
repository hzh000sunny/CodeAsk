import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MessageStream } from "../src/components/session/MessageStream";

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

  it("shows a composing indicator before the first token arrives", () => {
    const { container } = render(
      <MessageStream
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

    const indicator = screen.getByRole("status", { name: "CodeAsk 正在准备回答" });
    expect(indicator).toBeInTheDocument();
    expect(container.querySelector(".composing-ink")).toBeInTheDocument();
    expect(screen.getByText("正在落笔…")).toBeInTheDocument();
    // The bare blinking caret no longer stands in for the preparing beat.
    expect(container.querySelector(".stream-caret")).toBeNull();
  });
});
