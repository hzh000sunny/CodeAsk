import { fireEvent, render, screen, within } from "@testing-library/react";

import { InvestigationPanel } from "../src/components/session/InvestigationPanel";
import type {
  RuntimeInsight,
  RuntimeSessionState,
} from "../src/components/session/session-model";

describe("InvestigationPanel runtime previews", () => {
  const runtimeState: RuntimeSessionState = {
    configId: "cfg_glm",
    configName: "火山引擎 GLM-5.1",
    modelName: "glm-5.1",
    protocol: "openai_compatible",
    scope: "global",
    isGlobalPool: true,
    contextSizeChars: 32768,
    contextWindowChars: 200000,
    usageRatio: 32768 / 200000,
    usageLabel: "32k / 200k",
  };

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
        onPromoteAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        runtimeState={runtimeState}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Wiki 范围/ }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
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
        onPromoteAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        runtimeState={runtimeState}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /证据：回调 Runbook/ }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toBeInTheDocument();
    expect(
      within(dialog).getByRole("link", { name: "知识库/回调 Runbook" }),
    ).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=15&heading=%E5%9B%9E%E8%B0%83+Runbook+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4",
    );
    expect(
      within(dialog).getByText(/命中小节：回调 Runbook > 排查步骤/),
    ).toBeInTheDocument();
  });

  it("renders the runtime model status below the session data section", () => {
    render(
      <InvestigationPanel
        attachments={[]}
        insights={[]}
        isLoadingAttachments={false}
        isStreaming={false}
        onDeleteAttachment={() => undefined}
        onDescribeAttachment={() => undefined}
        onPromoteAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        runtimeState={runtimeState}
      />,
    );

    expect(screen.getByText("模型状态")).toBeInTheDocument();
    expect(screen.getByText("当前模型")).toBeInTheDocument();
    expect(screen.getByText("glm-5.1")).toBeInTheDocument();
    expect(screen.getByText("32k / 200k")).toBeInTheDocument();
    const rows = document.querySelectorAll(".session-runtime-row");
    expect(rows).toHaveLength(2);
  });

  it("shows expanded debug details for repo result previews", () => {
    const insights: RuntimeInsight[] = [
      {
        id: "repos_1",
        kind: "tool_result",
        title: "代码仓库完成",
        detail: "可用代码仓库 1 个 · 特性范围",
        status: "success",
        data: {
          tool_name: "list_code_repos",
          ok: true,
          summary: "可用代码仓库 1 个",
          items_count: 1,
          items_preview: [
            {
              repo_id: "repo_anything_llm",
              repo_name: "Manual continuity anything-llm 1778137237804",
              status: "ready",
            },
          ],
          version_info: {
            scope_source: "feature_scope",
            feature_ids: [3],
          },
        },
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
        onPromoteAttachment={() => undefined}
        onRenameAttachment={() => undefined}
        runtimeState={runtimeState}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /代码仓库完成/ }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(within(dialog).getByText("结果条数")).toBeInTheDocument();
    expect(within(dialog).getByText("1")).toBeInTheDocument();
    expect(within(dialog).getByText("结果预览")).toBeInTheDocument();
    expect(within(dialog).getByText(/repo_anything_llm/)).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Manual continuity anything-llm/),
    ).toBeInTheDocument();
  });
});
