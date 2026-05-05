import { fireEvent, render, screen, within } from "@testing-library/react";

import { InvestigationPanel } from "../src/components/session/InvestigationPanel";
import type { RuntimeInsight } from "../src/components/session/session-model";

describe("InvestigationPanel runtime previews", () => {
  it("renders markdown-rich wiki scope details inside the event popover", () => {
    const insights: RuntimeInsight[] = [
      {
        id: "scope_1",
        kind: "wiki_scope",
        title: "Wiki 范围：知识库、问题定位报告",
        detail: "显式命中 1 个节点，默认范围 2 个",
        detailMarkdown:
          "**默认范围**\n- [知识库](#/wiki?feature=7&node=2)\n- [问题定位报告](#/wiki?feature=7&node=3)\n\n**显式命中**\n- [知识库/支付回调](#/wiki?feature=7&node=10)",
      },
    ];

    render(
      <InvestigationPanel
        attachments={[]}
        insights={insights}
        isLoadingAttachments={false}
        isStreaming={false}
        onDeleteAttachment={() => undefined}
        onDescribeAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        stages={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Wiki 范围/ }));

    const dialog = screen.getByRole("dialog", { name: "运行事件详情" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("默认范围")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "知识库/支付回调" }),
    ).toHaveAttribute("href", "#/wiki?feature=7&node=10");
  });

  it("renders wiki evidence details as clickable links with heading context", () => {
    const insights: RuntimeInsight[] = [
      {
        id: "evidence_1",
        kind: "evidence",
        title: "证据：回调 Runbook",
        detail: "doc · 知识库/回调 Runbook · 回调 Runbook > 排查步骤",
        detailMarkdown:
          "[知识库/回调 Runbook](#/wiki?feature=7&node=15&heading=%E5%9B%9E%E8%B0%83+Runbook+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4)\n\n命中小节：回调 Runbook > 排查步骤",
      },
    ];

    render(
      <InvestigationPanel
        attachments={[]}
        insights={insights}
        isLoadingAttachments={false}
        isStreaming={false}
        onDeleteAttachment={() => undefined}
        onDescribeAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        stages={[]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /证据：回调 Runbook/ }));

    const dialog = screen.getByRole("dialog", { name: "运行事件详情" });
    expect(dialog).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "知识库/回调 Runbook" }),
    ).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=15&heading=%E5%9B%9E%E8%B0%83+Runbook+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4",
    );
    expect(within(dialog).getByText(/命中小节：回调 Runbook > 排查步骤/)).toBeInTheDocument();
  });
});
