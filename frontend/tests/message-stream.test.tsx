import { render } from "@testing-library/react";
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
});
