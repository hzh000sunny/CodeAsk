import type { AgentTraceResponse, SessionTurnResponse } from "../../types/api";
import type { AgentEvent } from "../../types/sse";
import {
  createInitialStages,
  runtimeInsightFromEvent,
  runtimeStateFromEvent,
  type ConversationMessage,
  type RuntimeInsight,
  type RuntimeSessionState,
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

export function featureIdsFromSessionTraces(traces: AgentTraceResponse[]) {
  const result: number[] = [];
  const seen = new Set<number>();
  for (const trace of traces) {
    const event = agentEventFromTrace(trace);
    if (!event) {
      continue;
    }
    const ids = featureIdsFromTraceValue(event.data);
    for (const id of ids) {
      if (seen.has(id)) {
        continue;
      }
      seen.add(id);
      result.push(id);
    }
  }
  return result;
}

export function runtimeStateFromSessionTraces(
  traces: AgentTraceResponse[],
): RuntimeSessionState | null {
  let latest: RuntimeSessionState | null = null;
  for (const trace of traces) {
    const event = agentEventFromTrace(trace);
    if (!event) {
      continue;
    }
    const runtimeState = runtimeStateFromEvent(event);
    if (runtimeState) {
      latest = runtimeState;
    }
  }
  return latest;
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
      insights.push({
        ...insight,
        id: trace.id,
        occurredAt: trace.created_at,
        turnId: trace.turn_id,
      });
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
  if (trace.event_type === "wiki_scope_resolution") {
    return {
      type: "wiki_scope_resolution",
      data: payload,
    };
  }
  if (trace.event_type === "retrieval_context") {
    return { type: "retrieval_context", data: payload };
  }
  if (trace.event_type === "runtime_state") {
    return { type: "runtime_state", data: payload };
  }
  if (trace.event_type === "llm_input") {
    return { type: "llm_input", data: payload };
  }
  if (trace.event_type === "tool_call") {
    return { type: "tool_call", data: payload };
  }
  if (trace.event_type === "tool_result") {
    return { type: "tool_result", data: payload };
  }
  if (trace.event_type === "needs_clarification") {
    return { type: "needs_clarification", data: payload };
  }
  if (trace.event_type === "assistant_action") {
    return { type: "assistant_action", data: payload };
  }
  if (trace.event_type === "error") {
    return { type: "error", data: payload };
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

function featureIdsFromTraceValue(value: unknown): number[] {
  const result: number[] = [];
  function visit(candidate: unknown) {
    if (Array.isArray(candidate)) {
      for (const item of candidate) {
        visit(item);
      }
      return;
    }
    if (!candidate || typeof candidate !== "object") {
      return;
    }
    for (const [key, child] of Object.entries(candidate)) {
      if (key === "feature_ids" && Array.isArray(child)) {
        for (const item of child) {
          if (typeof item === "number" && Number.isInteger(item)) {
            result.push(item);
          }
        }
        continue;
      }
      if (key === "feature_id" && typeof child === "number" && Number.isInteger(child)) {
        result.push(child);
        continue;
      }
      visit(child);
    }
  }
  visit(value);
  return result;
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
      const headingPath = stringValue(data.heading_path);
      const featureId =
        typeof data.feature_id === "number" && Number.isInteger(data.feature_id)
          ? data.feature_id
          : null;
      const nodeId =
        typeof data.node_id === "number" && Number.isInteger(data.node_id)
          ? data.node_id
          : null;
      const result = recordValue(data.result);
      const resultData = recordValue(result.data);
      const resultPath = stringValue(resultData.path);
      return {
        id,
        kind: "evidence",
        title: `证据：${summary}`,
        occurredAt: turn.created_at,
        turnId: turn.id,
        detail: [stringValue(row.type), path ?? resultPath, headingPath]
          .filter(Boolean)
          .join(" · "),
        detailMarkdown:
          featureId !== null && nodeId !== null
            ? [
                `[${path ?? summary}](#/wiki?${new URLSearchParams({
                  feature: String(featureId),
                  node: String(nodeId),
                  ...(headingPath ? { heading: headingPath } : {}),
                }).toString()})`,
                headingPath ? `命中小节：${headingPath}` : null,
              ]
                .filter(Boolean)
                .join("\n\n")
            : undefined,
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
