import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActionTraceEvent } from "../src/components/session/action-trace/ActionTraceEvent";
import {
  actionTraceFromAgentEvent,
  type ActionTraceEvent as ActionTraceEventModel,
} from "../src/components/session/action-trace/action-trace-model";

describe("action trace code scope display", () => {
  it("summarizes feature-scoped code tool results", () => {
    const event = actionTraceFromAgentEvent({
      type: "tool_result",
      data: {
        tool_call_id: "call_1",
        tool_name: "search_code",
        ok: true,
        summary: "命中 1 个代码位置",
        version_info: {
          scope_source: "feature_scope",
          feature_ids: [3, 7],
          repo_name: "claude-code",
          ref: "HEAD",
          commit: "683f7d2abcdef",
        },
      },
    });

    expect(event).not.toBeNull();
    expect(event?.detail).toContain("特性范围");
    expect(event?.detail).toContain("特性 3, 7");
    expect(event?.detail).toContain("claude-code");
  });

  it("shows code scope metadata in the action trace popover", () => {
    const event: ActionTraceEventModel = {
      id: "tool_result_call_1",
      kind: "tool_result",
      title: "代码搜索完成",
      detail: "命中 1 个代码位置",
      status: "success",
      data: {
        tool_call_id: "call_1",
        tool_name: "search_code",
        ok: true,
        summary: "命中 1 个代码位置",
        version_info: {
          scope_source: "explicit_user_repo",
          feature_ids: [],
          repo_id: "repo_123",
          repo_name: "claude-code",
          ref: "HEAD",
          commit: "683f7d2abcdef",
        },
      },
      evidenceRefs: [],
    };

    render(<ActionTraceEvent event={event} />);
    fireEvent.click(screen.getByRole("button", { name: "代码搜索完成 详情" }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("范围来源");
    expect(dialog).toHaveTextContent("用户显式仓库");
    expect(dialog).toHaveTextContent("仓库");
    expect(dialog).toHaveTextContent("claude-code(repo_123)");
    expect(dialog).toHaveTextContent("版本");
    expect(dialog).toHaveTextContent("HEAD");
    expect(dialog).toHaveTextContent("提交");
    expect(dialog).toHaveTextContent("683f7d2abcdef");
  });
});
