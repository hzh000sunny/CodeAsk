import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { WikiReader } from "../src/components/wiki/WikiReader";

describe("WikiReader heading anchors", () => {
  it("renders stable heading anchors and scrolls the requested heading into view", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });

    render(
      <WikiReader
        content={"# 总览\n\n## 排查步骤\n\n先看日志。"}
        headingTarget="排查步骤"
      />,
    );

    const heading = screen.getByRole("heading", { name: "排查步骤" });
    expect(heading).toHaveAttribute("id", "wiki-heading-排查步骤");

    await waitFor(() =>
      expect(scrollIntoView).toHaveBeenCalledWith({
        block: "start",
      }),
    );
  });
});
