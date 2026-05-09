import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AppFeedbackProvider,
  useAppFeedback,
} from "../src/components/feedback/AppFeedback";

function FeedbackHarness() {
  const { showError, showSuccess } = useAppFeedback();
  return (
    <div>
      <button onClick={() => showSuccess("仓库已保存")} type="button">
        success
      </button>
      <button
        onClick={() => showError("生成报告失败：Method Not Allowed")}
        type="button"
      >
        error
      </button>
    </div>
  );
}

describe("AppFeedbackProvider", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a centered success toast and dismisses it automatically", async () => {
    vi.useFakeTimers();
    render(
      <AppFeedbackProvider>
        <FeedbackHarness />
      </AppFeedbackProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "success" }));

    expect(screen.getByRole("status")).toHaveTextContent("仓库已保存");
    expect(screen.getByRole("status")).toHaveClass("app-feedback-toast");

    act(() => {
      vi.advanceTimersByTime(2600);
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a centered blocking error dialog", async () => {
    render(
      <AppFeedbackProvider>
        <FeedbackHarness />
      </AppFeedbackProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "error" }));

    expect(await screen.findByRole("alertdialog")).toHaveTextContent(
      "生成报告失败：Method Not Allowed",
    );
    expect(screen.getByRole("button", { name: "知道了" })).toBeInTheDocument();
  });
});
