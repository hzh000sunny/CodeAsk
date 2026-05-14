import { describe, expect, it } from "vitest";

import {
  appendRuntimeInsight,
  createInitialStages,
  runtimeInsightFromEvent,
  runtimeStateFromEvent,
} from "../src/components/session/session-model";
import { insightsFromSessionHistory } from "../src/components/session/session-history";
import type { AgentTraceResponse } from "../src/types/api";

describe("session runtime stage model", () => {
  it("orders knowledge retrieval before evidence sufficiency and code investigation", () => {
    const stages = createInitialStages();
    const keys = stages.map((stage) => stage.key);

    expect(keys).toEqual([
      "input_analysis",
      "scope_detection",
      "knowledge_retrieval",
      "sufficiency_judgement",
      "code_investigation",
      "answer_finalization",
    ]);
    expect(
      stages.find((stage) => stage.key === "scope_detection")?.detail,
    ).toBe("识别问题关联的特性和上下文范围");
    expect(
      stages.find((stage) => stage.key === "sufficiency_judgement")?.detail,
    ).toBe("判断知识证据是否足够回答");
  });

  it("maps wiki scope resolution events into readable runtime insights", () => {
    const insight = runtimeInsightFromEvent({
      type: "wiki_scope_resolution",
      data: {
        query: "支付回调超时",
        defaults: [
          { node_id: 2, path: "知识库", label: "知识库" },
          { node_id: 3, path: "问题定位报告", label: "问题定位报告" },
        ],
        matches: [
          {
            node_id: 10,
            path: "知识库/支付回调",
            label: "支付回调",
            match_reason: "contains",
            matched_phrase: "支付回调",
          },
        ],
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("wiki_scope");
    expect(insight?.title).toContain("Wiki 范围");
    expect(insight?.detail).toContain("显式命中 1 个节点");
    expect(insight?.detailMarkdown).toContain("知识库/支付回调");
    expect(insight?.detailMarkdown).toContain("**默认范围**");
  });

  it("uses per-item feature ids when rendering cross-feature wiki scope links", () => {
    const insight = runtimeInsightFromEvent({
      type: "wiki_scope_resolution",
      data: {
        feature_id: 1,
        feature_ids: [1, 2],
        query: "跨特性回调超时",
        defaults: [
          { feature_id: 1, node_id: 2, path: "知识库", label: "知识库" },
          { feature_id: 2, node_id: 12, path: "知识库", label: "知识库" },
        ],
        matches: [
          {
            feature_id: 2,
            node_id: 18,
            path: "知识库/支付回调",
            label: "支付回调",
            match_reason: "contains",
            matched_phrase: "支付回调",
          },
        ],
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.detailMarkdown).toContain("#/wiki?feature=2&node=18");
  });

  it("maps wiki evidence events into clickable markdown details with heading targets", () => {
    const insight = runtimeInsightFromEvent({
      type: "evidence",
      data: {
        item: {
          id: "ev_knowledge_1",
          title: "回调 Runbook",
          source: "doc",
          path: "知识库/回调 Runbook",
          heading_path: "回调 Runbook > 排查步骤",
          feature_id: 7,
          node_id: 15,
        },
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("evidence");
    expect(insight?.detail).toContain("回调 Runbook > 排查步骤");
    expect(insight?.detailMarkdown).toContain("#/wiki?feature=7&node=15");
    expect(insight?.detailMarkdown).toContain("heading=%E5%9B%9E%E8%B0%83+Runbook+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4");
  });

  it("maps reasoning diagnostics without exposing raw reasoning", () => {
    const insight = runtimeInsightFromEvent({
      type: "reasoning_observed",
      data: {
        field: "reasoning_content",
        length: 12,
        chunks: 3,
        redacted: false,
        raw_reasoning_used: false,
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("diagnostic");
    expect(insight?.title).toBe("模型推理已隔离");
    expect(insight?.detail).toContain("reasoning_content");
    expect(insight?.detail).toContain("分片 3");
    expect(String(insight)).not.toContain("内部思考");
  });

  it("maps opencode reasoning diagnostics using content_length", () => {
    const insight = runtimeInsightFromEvent({
      type: "reasoning_observed",
      data: {
        source: "opencode",
        part_id: "prt_reasoning",
        content_length: 42,
        redacted: true,
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.title).toBe("模型推理已隔离");
    expect(insight?.detail).toContain("长度 42");
    expect(insight?.data?.length).toBe(42);
  });

  it("maps opencode error payloads into readable messages", () => {
    const insight = runtimeInsightFromEvent({
      type: "error",
      data: {
        backend: "opencode",
        error: "opencode unavailable",
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.title).toBe("运行失败");
    expect(insight?.detail).toBe("opencode unavailable");
  });

  it("maps opencode busy into a running status insight", () => {
    const insight = runtimeInsightFromEvent({
      type: "assistant_action",
      data: {
        action: "opencode_busy",
        summary: "opencode session status: busy",
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("runtime_status");
    expect(insight?.title).toBe("opencode running");
    expect(insight?.status).toBe("running");
  });

  it("deduplicates opencode running and removes it when real events arrive", () => {
    const running = runtimeInsightFromEvent({
      type: "assistant_action",
      data: { action: "opencode_busy" },
    });
    const toolCall = runtimeInsightFromEvent({
      type: "tool_call",
      data: {
        tool_call_id: "call_1",
        tool_name: "codeask_list_features",
        arguments_summary: {},
      },
    });

    expect(running).not.toBeNull();
    expect(toolCall).not.toBeNull();

    const withOneRunning = appendRuntimeInsight([], {
      ...running!,
      turnId: "turn_1",
    });
    const stillOneRunning = appendRuntimeInsight(withOneRunning, {
      ...running!,
      id: "runtime_status_2",
      turnId: "turn_1",
    });
    const withRealEvent = appendRuntimeInsight(stillOneRunning, {
      ...toolCall!,
      turnId: "turn_1",
    });

    expect(withOneRunning).toHaveLength(1);
    expect(stillOneRunning).toHaveLength(1);
    expect(withRealEvent).toHaveLength(1);
    expect(withRealEvent[0].kind).toBe("tool_call");
  });

  it("does not restore persisted opencode busy events as history insights", () => {
    const traces: AgentTraceResponse[] = [
      trace("tr_busy_1", "turn_1", "assistant_action", {
        action: "opencode_busy",
      }),
      trace("tr_busy_2", "turn_1", "assistant_action", {
        action: "opencode_busy",
      }),
      trace("tr_tool", "turn_1", "tool_call", {
        tool_call_id: "call_1",
        tool_name: "codeask_list_features",
        arguments_summary: {},
      }),
      trace("tr_busy_3", "turn_1", "assistant_action", {
        action: "opencode_busy",
      }),
    ];

    const insights = insightsFromSessionHistory([], traces);

    expect(insights.map((insight) => insight.kind)).toEqual(["tool_call"]);
  });

  it("restores persisted reasoning diagnostics from session history", () => {
    const traces: AgentTraceResponse[] = [
      trace("tr_busy_1", "turn_1", "assistant_action", {
        action: "opencode_busy",
      }),
      trace("tr_reasoning_summary", "turn_1", "reasoning_observed", {
        field: "unknown",
        length: 152,
        chunks: 1,
        redacted: true,
        raw_reasoning_used: false,
      }),
    ];

    const insights = insightsFromSessionHistory([], traces);

    expect(insights).toHaveLength(1);
    expect(insights[0].kind).toBe("diagnostic");
    expect(insights[0].title).toBe("模型推理已隔离");
    expect(insights[0].detail).toContain("长度 152");
  });

  it("maps runtime state events into session header data", () => {
    const runtimeState = runtimeStateFromEvent({
      type: "runtime_state",
      data: {
        config_id: "cfg_glm",
        config_name: "火山引擎 GLM-5.1",
        model_name: "glm-5.1",
        protocol: "openai_compatible",
        context_size_chars: 32768,
        context_window_chars: 200000,
      },
    });

    expect(runtimeState).not.toBeNull();
    expect(runtimeState?.modelName).toBe("glm-5.1");
    expect(runtimeState?.configName).toBe("火山引擎 GLM-5.1");
    expect(runtimeState?.usageLabel).toBe("32k / 200k");
    expect(runtimeState?.usageRatio).toBeGreaterThan(0);
  });

  it("renders tiny runtime usage as readable k units instead of zero", () => {
    const runtimeState = runtimeStateFromEvent({
      type: "runtime_state",
      data: {
        backend: "opencode",
        context_size_chars: 12,
        context_window_chars: 200000,
        usage_label: "0k / 200k",
      },
    });

    expect(runtimeState).not.toBeNull();
    expect(runtimeState?.usageLabel).toBe("1k / 200k");
  });

  it("maps llm input audits into debug trace insights", () => {
    const insight = runtimeInsightFromEvent({
      type: "llm_input",
      data: {
        round: 2,
        messages_count: 8,
        tools_count: 11,
        context_size_chars: 15337,
        recent_tool_results: [
          {
            tool: "list_code_repos",
            ok: true,
            summary: "可用代码仓库 1 个",
            items_count: 1,
            repos: [
              {
                repo_id: "repo_anything_llm",
                repo_name: "Manual continuity anything-llm 1778137237804",
              },
            ],
          },
        ],
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("diagnostic");
    expect(insight?.title).toBe("模型输入审计");
    expect(insight?.detail).toContain("第 2 轮");
    expect(insight?.detail).toContain("8 条消息");
    expect(insight?.detailMarkdown).toContain("Manual continuity anything-llm");
    expect(insight?.detailMarkdown).toContain("repo_anything_llm");
  });

  it("maps UI reasoning leak diagnostics without exposing raw text", () => {
    const insight = runtimeInsightFromEvent({
      type: "reasoning_leak_detected",
      data: {
        marker: "think",
        mode: "mask_in_ui",
        leakedLength: 18,
        masked: true,
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("warning");
    expect(insight?.title).toBe("检测到推理泄漏");
    expect(insight?.detail).toContain("已在界面遮蔽");
  });
});

function trace(
  id: string,
  turnId: string,
  eventType: string,
  payload: unknown,
): AgentTraceResponse {
  return {
    id,
    session_id: "sess_1",
    turn_id: turnId,
    stage: "chat_runtime",
    event_type: eventType,
    payload,
    created_at: "2026-05-14T00:00:00Z",
    updated_at: "2026-05-14T00:00:00Z",
  };
}
