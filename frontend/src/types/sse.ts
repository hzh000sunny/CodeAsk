export type AgentEventName =
  | "llm_input"
  | "stage_transition"
  | "text_delta"
  | "reasoning_observed"
  | "reasoning_leak_detected"
  | "runtime_state"
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
