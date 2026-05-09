import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionTraceEvent } from "../src/components/session/action-trace/ActionTraceEvent";
import { ActionTracePanel } from "../src/components/session/action-trace/ActionTracePanel";
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

  it("shows warning, truncation and raw result metadata in the action trace popover", () => {
    const event: ActionTraceEventModel = {
      id: "tool_result_call_2",
      kind: "tool_result",
      title: "代码搜索失败",
      detail: "命中 0 个代码位置",
      status: "error",
      data: {
        tool_call_id: "call_2",
        tool_name: "search_code",
        ok: false,
        summary: "命中 0 个代码位置",
        truncated: true,
        raw_result_ref: "raw_tool_result:sess_1:turn_1:search_code:deadbeef",
        warnings: ["0 命中不代表代码不存在，请先确认目录和命名。"],
        error_type: "needs_clarification",
        message: "当前关键词没有直接命中，请先确认代码目录。",
        version_info: {
          scope_source: "feature_scope",
          feature_ids: [3],
          repo_name: "anything-llm",
          ref: "HEAD",
          commit: "1234567890ab",
        },
      },
      evidenceRefs: [],
    };

    render(<ActionTraceEvent event={event} />);
    fireEvent.click(screen.getByRole("button", { name: "代码搜索失败 详情" }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("提醒");
    expect(dialog).toHaveTextContent("0 命中不代表代码不存在");
    expect(dialog).toHaveTextContent("结果已截断");
    expect(dialog).toHaveTextContent("原始结果");
    expect(dialog).toHaveTextContent("raw_tool_result:sess_1:turn_1:search_code:deadbeef");
    expect(dialog).toHaveTextContent("错误类型");
    expect(dialog).toHaveTextContent("needs_clarification");
    expect(dialog).toHaveTextContent("错误信息");
    expect(dialog).toHaveTextContent("当前关键词没有直接命中");
  });

  it("copies long detail values from the action trace popover", async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    const event: ActionTraceEventModel = {
      id: "tool_result_call_copy",
      kind: "tool_result",
      title: "代码文件完成",
      detail: "读取代码文件成功",
      status: "success",
      data: {
        tool_call_id: "call_copy",
        tool_name: "read_code_file",
        ok: true,
        summary: "读取代码文件成功",
        path: "server/prisma/schema.prisma",
        raw_result_ref: "raw_tool_result:sess_long:turn_long:read_code_file:abcdef1234567890",
      },
      evidenceRefs: [],
    };

    render(<ActionTraceEvent event={event} />);
    fireEvent.click(screen.getByRole("button", { name: "代码文件完成 详情" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "复制 路径" }));
      await Promise.resolve();
    });

    expect(writeText).toHaveBeenCalledWith("server/prisma/schema.prisma");
    expect(screen.getByText("已复制")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(1300);
    });
    expect(screen.queryByText("已复制")).not.toBeInTheDocument();
    vi.useRealTimers();
  });

  it("renders per-turn summary as stable metric chips including zero values", () => {
    const events: ActionTraceEventModel[] = [
      {
        id: "event_1",
        kind: "retrieval",
        title: "已准备 2 条上下文",
        detail: "1 个候选特性 · 1 条 Wiki",
        status: "info",
        turnId: "turn_1",
        evidenceRefs: [],
        data: {},
      },
      {
        id: "event_2",
        kind: "tool_call",
        title: "准备使用 代码搜索",
        detail: "query=buddy",
        status: "running",
        turnId: "turn_1",
        evidenceRefs: [],
        data: {
          tool_name: "search_code",
        },
      },
      {
        id: "event_3",
        kind: "tool_result",
        title: "代码搜索完成",
        detail: "命中 1 个代码位置",
        status: "success",
        turnId: "turn_1",
        evidenceRefs: [{ path: "src/buddy/CompanionSprite.tsx" }],
        data: {
          tool_name: "search_code",
        },
      },
      {
        id: "event_4",
        kind: "tool_result",
        title: "代码文件完成",
        detail: "读取代码文件成功",
        status: "success",
        turnId: "turn_1",
        evidenceRefs: [],
        data: {
          tool_name: "read_code_file",
        },
      },
    ];

    render(<ActionTracePanel events={events} isStreaming={false} />);

    expect(screen.getByText("第 1 轮")).toBeInTheDocument();
    const summary = screen.getByLabelText("第 1 轮 摘要");
    expect(summary).toHaveTextContent("4动作");
    expect(summary).toHaveTextContent("3工具");
    expect(summary).toHaveTextContent("1证据");
    expect(summary).toHaveTextContent("1读码");
    expect(summary).toHaveTextContent("0提醒");
    expect(summary).toHaveTextContent("0失败");

    const warningMetric = screen.getByText("提醒").closest(".action-trace-turn-metric");
    const errorMetric = screen.getByText("失败").closest(".action-trace-turn-metric");
    expect(warningMetric).toHaveAttribute("data-zero", "true");
    expect(errorMetric).toHaveAttribute("data-zero", "true");
  });
});
