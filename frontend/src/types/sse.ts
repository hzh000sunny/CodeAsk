export type AgentEventName =
  | "stage_transition"
  | "text_delta"
  | "tool_call"
  | "tool_result"
  | "evidence"
  | "scope_detection"
  | "sufficiency_judgement"
  | "ask_user"
  | "done"
  | "error";

export interface AgentEvent {
  type: AgentEventName;
  data: Record<string, unknown>;
}
