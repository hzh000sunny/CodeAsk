import { ApiError } from "./api";
import { getGuestLlmConfig, getSubjectId } from "./identity";
import type { AgentEvent, AgentEventName } from "../types/sse";

const AGENT_EVENT_NAMES = new Set<AgentEventName>([
  "llm_input",
  "stage_transition",
  "text_delta",
  "reasoning_observed",
  "reasoning_leak_detected",
  "runtime_state",
  "tool_call",
  "tool_result",
  "retrieval_context",
  "assistant_action",
  "needs_clarification",
  "evidence",
  "wiki_scope_resolution",
  "scope_detection",
  "sufficiency_judgement",
  "ask_user",
  "done",
  "error",
]);

interface StreamSessionMessageInput {
  sessionId: string;
  content: string;
  client_turn_id?: string;
  feature_ids?: number[];
  repo_bindings?: Array<{ repo_id: string; ref: string }>;
  reply_to?: string | null;
  onEvent: (event: AgentEvent) => void;
  onTurnId?: (turnId: string) => void;
  signal?: AbortSignal;
}

export async function streamSessionMessage({
  sessionId,
  content,
  client_turn_id,
  feature_ids = [],
  repo_bindings = [],
  reply_to = null,
  onEvent,
  onTurnId,
  signal,
}: StreamSessionMessageInput) {
  const guestLlmConfig = getCompleteGuestLlmConfig();
  const response = await fetch(`/api/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Subject-Id": getSubjectId(),
    },
    body: JSON.stringify({
      content,
      client_turn_id,
      feature_ids,
      repo_bindings,
      reply_to,
      ...(guestLlmConfig ? { guest_llm_config: guestLlmConfig } : {}),
    }),
    signal,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (!response.body) {
    throw new Error("SSE response did not include a readable body");
  }
  const turnId = response.headers.get("X-CodeAsk-Turn-Id");
  if (turnId) {
    onTurnId?.(turnId);
  }

  const handleEvent = (event: AgentEvent) => {
    const eventTurnId = event.data.turn_id;
    if (typeof eventTurnId === "string" && eventTurnId.length > 0) {
      onTurnId?.(eventTurnId);
    }
    onEvent(event);
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = dispatchBufferedEvents(buffer, handleEvent);
  }

  buffer += decoder.decode();
  dispatchBufferedEvents(`${buffer}\n\n`, handleEvent);
}

async function readError(response: Response) {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function dispatchBufferedEvents(
  buffer: string,
  onEvent: (event: AgentEvent) => void,
) {
  let remaining = buffer;
  while (remaining.includes("\n\n")) {
    const index = remaining.indexOf("\n\n");
    const block = remaining.slice(0, index);
    remaining = remaining.slice(index + 2);
    const event = parseEventBlock(block);
    if (event) {
      onEvent(event);
    }
  }
  return remaining;
}

function parseEventBlock(block: string): AgentEvent | null {
  let type: AgentEventName | null = null;
  const dataLines: string[] = [];

  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) {
      const name = line.slice("event:".length).trim();
      type = isAgentEventName(name) ? name : null;
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (!type) {
    return null;
  }

  const dataText = dataLines.join("\n");
  return {
    type,
    data: dataText ? parseJsonData(dataText) : {},
  };
}

function parseJsonData(dataText: string) {
  try {
    const parsed = JSON.parse(dataText) as unknown;
    return isRecord(parsed) ? parsed : { value: parsed };
  } catch {
    return { text: dataText };
  }
}

function isAgentEventName(value: string): value is AgentEventName {
  return AGENT_EVENT_NAMES.has(value as AgentEventName);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getCompleteGuestLlmConfig() {
  const config = getGuestLlmConfig();
  if (!config?.api_key || !config.model_name) {
    return null;
  }
  return config;
}
