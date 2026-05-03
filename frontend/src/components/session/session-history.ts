import type { AgentTraceResponse, SessionTurnResponse } from "../../types/api";
import type { AgentEvent } from "../../types/sse";
import {
  createInitialStages,
  runtimeInsightFromEvent,
  type ConversationMessage,
  type RuntimeInsight,
} from "./session-model";

const STAGE_LABELS: Record<string, string> = {
  input_analysis: "输入分析",
  scope_detection: "范围判断",
  knowledge_retrieval: "知识检索",
  sufficiency_judgement: "充分性判断",
  code_investigation: "代码调查",
  evidence_synthesis: "证据合成",
  answer_finalization: "最终回答",
  report_drafting: "报告草稿",
  ask_user: "等待补充",
};

export function featureIdsFromEvent(data: Record<string, unknown>) {
  const value = data.feature_ids;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (item): item is number =>
      typeof item === "number" && Number.isInteger(item),
  );
}

export function messagesFromSessionTurns(
  turns: SessionTurnResponse[],
): ConversationMessage[] {
  return turns.map((turn) => ({
    id: turn.id,
    role: turn.role === "agent" ? "assistant" : "user",
    content: turn.content,
    status: turn.role === "agent" ? "done" : undefined,
    turnId: turn.role === "agent" ? turn.id : undefined,
  }));
}

export function stagesFromSessionTraces(traces: AgentTraceResponse[]) {
  const visibleTraces = traces.filter((trace) => !isHiddenStage(trace.stage));
  if (visibleTraces.length === 0) {
    return createInitialStages();
  }

  const stageRows = createInitialStages();
  const byKey = new Map(stageRows.map((stage) => [stage.key, stage]));
  for (const trace of visibleTraces) {
    if (!byKey.has(trace.stage)) {
      byKey.set(trace.stage, {
        key: trace.stage,
        label: STAGE_LABELS[trace.stage] ?? trace.stage,
        detail: "Agent 进入该阶段",
        status: "pending",
      });
    }
  }

  for (const trace of visibleTraces) {
    const stage = byKey.get(trace.stage);
    if (!stage) {
      continue;
    }
    if (trace.event_type === "stage_enter") {
      stage.status = stage.status === "done" ? "done" : "active";
      stage.detail = "Agent 已进入该阶段";
    }
    if (trace.event_type === "stage_exit") {
      stage.status = tracePayloadHasError(trace.payload) ? "error" : "done";
      stage.detail = stageExitDetail(trace.payload);
    }
  }

  return Array.from(byKey.values());
}

export function insightsFromSessionHistory(
  turns: SessionTurnResponse[],
  traces: AgentTraceResponse[],
): RuntimeInsight[] {
  const insights: RuntimeInsight[] = [];
  for (const trace of traces) {
    const event = agentEventFromTrace(trace);
    if (!event) {
      continue;
    }
    const insight = runtimeInsightFromEvent(event);
    if (insight) {
      insights.push({ ...insight, id: trace.id });
    }
  }
  for (const turn of turns) {
    for (const insight of evidenceInsightsFromTurn(turn)) {
      insights.push(insight);
    }
  }
  return insights;
}

function agentEventFromTrace(trace: AgentTraceResponse): AgentEvent | null {
  const payload = recordValue(trace.payload);
  if (trace.event_type === "scope_decision") {
    return {
      type: "scope_detection",
      data: recordValue(payload.output),
    };
  }
  if (trace.event_type === "sufficiency_decision") {
    return {
      type: "sufficiency_judgement",
      data: recordValue(payload.output),
    };
  }
  if (trace.event_type === "tool_call") {
    return { type: "tool_call", data: payload };
  }
  if (trace.event_type === "tool_result") {
    return { type: "tool_result", data: payload };
  }
  if (trace.event_type !== "llm_event") {
    return null;
  }
  if (payload.type === "tool_call_done") {
    return { type: "tool_call", data: recordValue(payload.data) };
  }
  if (payload.type === "error") {
    return { type: "error", data: recordValue(payload.data) };
  }
  return null;
}

function evidenceInsightsFromTurn(turn: SessionTurnResponse): RuntimeInsight[] {
  const evidence = recordValue(turn.evidence);
  const items = Array.isArray(evidence.items) ? evidence.items : [];
  return items
    .map((item, index) => {
      const row = recordValue(item);
      const id = stringValue(row.id) ?? `${turn.id}_evidence_${index}`;
      const summary = stringValue(row.summary) ?? "已收集证据";
      const data = recordValue(row.data);
      const path = stringValue(data.path);
      const result = recordValue(data.result);
      const resultData = recordValue(result.data);
      const resultPath = stringValue(resultData.path);
      return {
        id,
        kind: "evidence",
        title: `证据：${summary}`,
        detail: [stringValue(row.type), path ?? resultPath]
          .filter(Boolean)
          .join(" · "),
      };
    })
    .filter((item) => item.detail || item.title);
}

function isHiddenStage(stage: string) {
  return stage === "initialize" || stage === "terminate";
}

function tracePayloadHasError(payload: unknown) {
  const result = recordValue(recordValue(payload).result);
  return typeof result.error === "string" && result.error.length > 0;
}

function stageExitDetail(payload: unknown) {
  const result = recordValue(recordValue(payload).result);
  const error = stringValue(result.error);
  if (error) {
    return `阶段失败：${error}`;
  }
  const next = stringValue(result.next);
  return next ? `已完成，下一步：${STAGE_LABELS[next] ?? next}` : "已完成";
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}
