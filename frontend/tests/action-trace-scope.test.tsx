import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ActionTraceEvent } from "../src/components/session/action-trace/ActionTraceEvent";
import { ActionTracePanel } from "../src/components/session/action-trace/ActionTracePanel";
import {
  actionTraceFromAgentEvent,
  type ActionTraceEvent as ActionTraceEventModel,
} from "../src/components/session/action-trace/action-trace-model";
import { redactTraceDisplayText } from "../src/components/session/action-trace/path-redaction";

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

  it("shows malformed tool argument diagnostics in the action trace popover", () => {
    const event = actionTraceFromAgentEvent({
      type: "tool_call",
      data: {
        tool_call_id: "call_bad_json",
        tool_name: "search_wiki",
        arguments_summary: {},
        arguments_parse_error: "Expecting value",
        raw_arguments: '{"query":',
      },
    });

    expect(event).not.toBeNull();
    expect(event?.detail).toContain("参数 JSON 解析失败");

    render(<ActionTraceEvent event={event as ActionTraceEventModel} />);
    fireEvent.click(screen.getByRole("button", { name: "准备使用 Wiki 搜索 详情" }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("参数解析错误");
    expect(dialog).toHaveTextContent("Expecting value");
    expect(dialog).toHaveTextContent("原始参数");
    expect(dialog).toHaveTextContent('{"query":');
  });

  it("labels opencode task tool calls as subtask events", () => {
    const event = actionTraceFromAgentEvent({
      type: "tool_call",
      data: {
        tool_call_id: "call_task",
        tool_name: "task",
        arguments_summary: {
          description: "Explore AnythingLLM Embedding",
          subagent_type: "explore",
        },
      },
    });

    expect(event).not.toBeNull();
    expect(event?.title).toBe("准备使用 opencode 子任务");
    expect(event?.detail).toContain("Explore AnythingLLM Embedding");
    expect(event?.detail).toContain("explore");
  });

  it("labels opencode task tool results as subtask completion", () => {
    const event = actionTraceFromAgentEvent({
      type: "tool_result",
      data: {
        tool_call_id: "call_task",
        tool_name: "task",
        ok: true,
        summary: "Explore AnythingLLM Embedding",
      },
    });

    expect(event).not.toBeNull();
    expect(event?.title).toBe("opencode 子任务完成");
    expect(event?.detail).toContain("Explore AnythingLLM Embedding");
  });

  it("shows agent event timing diagnostics in the action trace popover", () => {
    const event: ActionTraceEventModel = {
      id: "runtime_state_1",
      kind: "runtime_status",
      title: "运行状态",
      detail: "opencode 正在处理当前请求",
      status: "running",
      data: {
        action: "opencode_busy",
        timing: {
          event_index: 4,
          turn_elapsed_ms: 123.45,
          since_previous_event_ms: 3.2,
          model_send_duration_ms: 2400,
          first_backend_event_wait_ms: 88,
          first_response_wait_ms: 1200,
          response_observed: true,
          total_elapsed_ms: 5200,
        },
      },
      evidenceRefs: [],
    };

    render(<ActionTraceEvent event={event} />);
    fireEvent.click(screen.getByRole("button", { name: "运行状态 详情" }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("事件序号");
    expect(dialog).toHaveTextContent("4");
    expect(dialog).toHaveTextContent("本轮已耗时");
    expect(dialog).toHaveTextContent("123.45 ms");
    expect(dialog).toHaveTextContent("提交模型耗时");
    expect(dialog).toHaveTextContent("2.40 s");
    expect(dialog).toHaveTextContent("等待后端事件");
    expect(dialog).toHaveTextContent("88 ms");
    expect(dialog).toHaveTextContent("等待首次响应");
    expect(dialog).toHaveTextContent("1.20 s");
    expect(dialog).toHaveTextContent("是否已有响应");
    expect(dialog).toHaveTextContent("是");
    expect(dialog).toHaveTextContent("总耗时");
    expect(dialog).toHaveTextContent("5.20 s");
  });

  it("maps done events so final turn duration can be inspected", () => {
    const event = actionTraceFromAgentEvent({
      type: "done",
      data: {
        backend: "opencode",
        timing: {
          event_index: 9,
          turn_elapsed_ms: 5200,
          response_observed: true,
          total_elapsed_ms: 5200,
        },
      },
    });

    expect(event).not.toBeNull();
    expect(event?.title).toBe("本轮完成");

    render(<ActionTraceEvent event={event as ActionTraceEventModel} />);
    fireEvent.click(screen.getByRole("button", { name: "本轮完成 详情" }));

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("总耗时");
    expect(dialog).toHaveTextContent("5.20 s");
    expect(dialog).toHaveTextContent("是否已有响应");
    expect(dialog).toHaveTextContent("是");
  });

  it("redacts host absolute paths in action trace cards and popovers", async () => {
    const absoluteWorkspacePath =
      "/home/hzh/.codeask/agent_sessions/opencode/sessions/sess_secret/workspace/repos/claude-code/src/tools/read.ts";
    const externalPath = "/home/hzh/.ssh/id_rsa";
    const event = actionTraceFromAgentEvent({
      type: "tool_call",
      data: {
        tool_call_id: "call_read_file",
        tool_name: "read",
        arguments_summary: {
          filePath: absoluteWorkspacePath,
          externalPath,
        },
        raw_arguments: JSON.stringify({
          filePath: absoluteWorkspacePath,
          externalPath,
        }),
      },
    });

    expect(event).not.toBeNull();
    render(<ActionTraceEvent event={event as ActionTraceEventModel} />);

    const card = screen.getByRole("button", { name: "准备使用 read 详情" });
    expect(card).toHaveTextContent(
      "workspace/repos/claude-code/src/tools/read.ts",
    );
    expect(card).not.toHaveTextContent("/home/hzh");
    expect(card).not.toHaveTextContent("sess_secret");
    fireEvent.click(card);

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent(
      "workspace/repos/claude-code/src/tools/read.ts",
    );
    expect(dialog).toHaveTextContent("[外部绝对路径已隐藏]");
    expect(dialog).not.toHaveTextContent("/home/hzh");
    expect(dialog).not.toHaveTextContent("sess_secret");
  });

  it("redacts read tool result paths under the current opencode session directory", () => {
    const absoluteWorkspacePath =
      "/home/hzh/.codeask/agent_sessions/opencode/sessions/sess_secret/workspace/repos/claude-code/src/tools/read.ts";
    const event = actionTraceFromAgentEvent({
      type: "tool_result",
      data: {
        tool_call_id: "call_read_file",
        tool_name: "read",
        ok: true,
        summary: `Read ${absoluteWorkspacePath}`,
        message: `Opened ${absoluteWorkspacePath}`,
        path: absoluteWorkspacePath,
      },
    });

    expect(event).not.toBeNull();
    render(<ActionTraceEvent event={event as ActionTraceEventModel} />);

    const card = screen.getByRole("button", { name: "read完成 详情" });
    expect(card).toHaveTextContent("workspace/repos/claude-code/src/tools/read.ts");
    expect(card).not.toHaveTextContent("/home/hzh");
    expect(card).not.toHaveTextContent("sess_secret");
    fireEvent.click(card);

    const dialog = screen.getByRole("dialog", { name: "Agent 行动详情" });
    expect(dialog).toHaveTextContent("workspace/repos/claude-code/src/tools/read.ts");
    expect(dialog).not.toHaveTextContent("/home/hzh");
    expect(dialog).not.toHaveTextContent("sess_secret");
  });

  it("redacts opencode tool result paths even when the leading slash is missing", () => {
    const slashlessWorkspacePath =
      "home/hzh/.codeask/agent_sessions/opencode/sessions/sess_secret/workspace/repos/claude-code/src/tools/read.ts";
    const event = actionTraceFromAgentEvent({
      type: "tool_result",
      data: {
        tool_call_id: "call_read_file",
        tool_name: "read",
        ok: true,
        summary: slashlessWorkspacePath,
        message: `Opened ${slashlessWorkspacePath}`,
      },
    });

    expect(event).not.toBeNull();
    render(<ActionTraceEvent event={event as ActionTraceEventModel} />);

    const card = screen.getByRole("button", { name: "read完成 详情" });
    expect(card).toHaveTextContent("workspace/repos/claude-code/src/tools/read.ts");
    expect(card).not.toHaveTextContent("homeworkspace");
    expect(card).not.toHaveTextContent("home/hzh");
    expect(card).not.toHaveTextContent("sess_secret");
  });

  it("redacts slashless opencode paths to the exact workspace relative path", () => {
    const slashlessWorkspacePath =
      "home/hzh/.codeask/agent_sessions/opencode/sessions/sess_secret/workspace/repos/claude-code/src/tools/read.ts";

    expect(redactTraceDisplayText(slashlessWorkspacePath)).toBe(
      "workspace/repos/claude-code/src/tools/read.ts",
    );
    expect(redactTraceDisplayText(`Opened ${slashlessWorkspacePath}`)).toBe(
      "Opened workspace/repos/claude-code/src/tools/read.ts",
    );
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
