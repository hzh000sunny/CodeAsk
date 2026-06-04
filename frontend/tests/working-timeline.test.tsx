import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { WorkingTimeline } from "../src/components/session/WorkingTimeline";
import type { ActionTraceEvent } from "../src/components/session/action-trace/action-trace-model";

const EVENTS: ActionTraceEvent[] = [
  {
    id: "retrieval_1",
    kind: "retrieval",
    title: "已准备 12 条上下文",
    detail: "12 条 Wiki · 3 份报告",
    status: "info",
  },
  {
    id: "tool_call_1",
    kind: "tool_call",
    title: "准备使用 代码搜索",
    detail: "query=token_expiry",
    status: "running",
  },
  {
    id: "evidence_1",
    kind: "evidence",
    title: "收集到 1 条证据",
    detail: "auth/middleware.py",
    status: "success",
  },
];

describe("WorkingTimeline", () => {
  it("renders nothing for a finished turn with no events", () => {
    const { container } = render(<WorkingTimeline events={[]} live={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a thinking shimmer while live with no events yet", () => {
    render(<WorkingTimeline events={[]} live />);
    expect(screen.getByText("正在分析问题…")).toBeInTheDocument();
  });

  it("starts expanded while live and lists every step with a status", () => {
    render(<WorkingTimeline events={EVENTS} live />);

    expect(screen.getByText("调查进行中")).toBeInTheDocument();
    const steps = screen.getByRole("list");
    const items = within(steps).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[1]).toHaveAttribute("data-status", "running");
    expect(items[2]).toHaveAttribute("data-status", "success");
    expect(screen.getByText("query=token_expiry")).toBeInTheDocument();
  });

  it("starts collapsed for a finished turn and expands on demand", () => {
    render(<WorkingTimeline events={EVENTS} live={false} />);

    // Collapsed: the summary is visible but the step list is not rendered.
    expect(screen.getByText("调查过程")).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /调查过程/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getByText("收集到 1 条证据")).toBeInTheDocument();
  });
});
