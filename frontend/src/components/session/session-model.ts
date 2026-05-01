import type { AgentEvent } from "../../types/sse";

export type MessageRole = "user" | "assistant" | "system";

export interface ConversationMessage {
  id: string;
  role: MessageRole;
  content: string;
  status?: "streaming" | "done" | "error";
}

export interface RuntimeStage {
  key: string;
  label: string;
  detail: string;
  status: "pending" | "active" | "done" | "error";
}

export interface RuntimeInsight {
  id: string;
  kind: string;
  title: string;
  detail: string;
}

const STAGE_LABELS: Record<string, string> = {
  input_analysis: "输入分析",
  scope_detection: "范围判断",
  knowledge_retrieval: "知识检索",
  sufficiency_judgement: "充分性判断",
  code_investigation: "代码调查",
  evidence_synthesis: "证据合成",
  answer_finalization: "最终回答",
  report_drafting: "报告草稿",
  ask_user: "等待补充"
};

export function createInitialStages(): RuntimeStage[] {
  return [
    { key: "input_analysis", label: "输入分析", detail: "等待会话输入", status: "pending" },
    { key: "scope_detection", label: "范围判断", detail: "识别问题关联的特性和上下文范围", status: "pending" },
    { key: "knowledge_retrieval", label: "知识检索", detail: "检索 Wiki 和问题报告", status: "pending" },
    { key: "sufficiency_judgement", label: "充分性判断", detail: "判断知识证据是否足够回答", status: "pending" },
    { key: "code_investigation", label: "代码调查", detail: "知识不足或用户强制时读取仓库证据", status: "pending" },
    { key: "answer_finalization", label: "最终回答", detail: "输出结论与可执行步骤", status: "pending" }
  ];
}

export function reduceStages(stages: RuntimeStage[], event: AgentEvent): RuntimeStage[] {
  if (event.type === "done") {
    return stages.map((stage) => ({ ...stage, status: "done" }));
  }
  if (event.type === "error") {
    return stages.map((stage) => (stage.status === "active" ? { ...stage, status: "error" } : stage));
  }
  if (event.type !== "stage_transition") {
    return stages;
  }

  const stageKey = stringData(event, "to") ?? stringData(event, "stage");
  if (!stageKey) {
    return stages;
  }

  const knownIndex = stages.findIndex((stage) => stage.key === stageKey);
  const nextStages =
    knownIndex === -1
      ? [...stages, { key: stageKey, label: stageLabel(stageKey, event), detail: "Agent 进入该阶段", status: "pending" as const }]
      : stages;
  const targetIndex = knownIndex === -1 ? nextStages.length - 1 : knownIndex;

  return nextStages.map((stage, index) => {
    if (index < targetIndex) {
      return { ...stage, status: "done" };
    }
    if (index === targetIndex) {
      return {
        ...stage,
        label: stageLabel(stage.key, event),
        detail: stringData(event, "message") ?? stage.detail,
        status: "active"
      };
    }
    return { ...stage, status: "pending" };
  });
}

export function textDeltaFromEvent(event: AgentEvent) {
  if (event.type !== "text_delta") {
    return "";
  }
  return stringData(event, "delta") ?? stringData(event, "text") ?? "";
}

export function runtimeInsightFromEvent(event: AgentEvent): RuntimeInsight | null {
  if (event.type === "scope_detection") {
    const featureIds = Array.isArray(event.data.feature_ids) ? event.data.feature_ids.join(", ") : "未命中特性";
    const confidence = numberData(event, "confidence");
    const confidenceText = confidence === null ? "" : ` · 置信度 ${Math.round(confidence * 100)}%`;
    return {
      id: `scope_${Date.now()}`,
      kind: "scope",
      title: `范围判断：${featureIds}${confidenceText}`,
      detail: stringData(event, "reason") ?? "Agent 已完成特性范围判断"
    };
  }
  if (event.type === "sufficiency_judgement") {
    return {
      id: `sufficiency_${Date.now()}`,
      kind: "sufficiency",
      title: stringData(event, "verdict") ?? "充分性判断",
      detail: [
        stringData(event, "reason"),
        stringData(event, "next") ? `下一步：${stringData(event, "next")}` : null
      ].filter(Boolean).join(" · ") || "Agent 已判断当前证据是否足够"
    };
  }
  if (event.type === "tool_call") {
    return {
      id: `tool_call_${stringData(event, "id") ?? Date.now()}`,
      kind: "tool",
      title: `调用工具：${stringData(event, "name") ?? "unknown"}`,
      detail: compactJson(event.data.arguments)
    };
  }
  if (event.type === "tool_result") {
    return {
      id: `tool_result_${stringData(event, "id") ?? Date.now()}`,
      kind: "tool",
      title: `工具结果：${stringData(event, "id") ?? "unknown"}`,
      detail: compactJson(event.data.result)
    };
  }
  if (event.type === "evidence") {
    const item = recordData(event, "item");
    return {
      id: stringValue(item?.id) ?? `evidence_${Date.now()}`,
      kind: "evidence",
      title: `证据：${stringValue(item?.title) ?? stringValue(item?.id) ?? "已收集"}`,
      detail: [stringValue(item?.source), stringValue(item?.locator), stringValue(item?.path)]
        .filter(Boolean)
        .join(" · ") || compactJson(item)
    };
  }
  if (event.type === "ask_user") {
    return {
      id: stringData(event, "ask_id") ?? `ask_${Date.now()}`,
      kind: "ask_user",
      title: "等待补充",
      detail: stringData(event, "question") ?? "Agent 需要更多信息"
    };
  }
  if (event.type === "error") {
    return {
      id: `error_${Date.now()}`,
      kind: "error",
      title: stringData(event, "code") ?? "运行错误",
      detail: stringData(event, "message") ?? "Agent 运行失败"
    };
  }
  return null;
}

export function askUserMessageFromEvent(event: AgentEvent) {
  if (event.type !== "ask_user") {
    return "";
  }
  const question = stringData(event, "question");
  return question ? `需要补充：${question}` : "需要补充：Agent 需要更多信息";
}

export function messageFromError(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "会话请求失败";
}

function stageLabel(stageKey: string, event: AgentEvent) {
  return stringData(event, "label") ?? STAGE_LABELS[stageKey] ?? stageKey;
}

function stringData(event: AgentEvent, key: string) {
  const value = event.data[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberData(event: AgentEvent, key: string) {
  const value = event.data[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function recordData(event: AgentEvent, key: string) {
  const value = event.data[key];
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function compactJson(value: unknown) {
  if (value === undefined || value === null) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
