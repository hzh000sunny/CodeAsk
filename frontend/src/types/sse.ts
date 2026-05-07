export type AgentEventName =
  | "stage_transition"
  | "text_delta"
  | "tool_call"
  | "tool_result"
  | "retrieval_context"
  | "assistant_action"
  | "needs_clarification"
  | "evidence"
  | "wiki_scope_resolution"
  | "scope_detection"
  | "sufficiency_judgement"
  | "ask_user"
  | "done"
  | "error";

export interface AgentEvent {
  type: AgentEventName;
  data: Record<string, unknown>;
}
