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
});
