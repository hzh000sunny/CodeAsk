export type LlmScope = "user" | "global";
export type LlmProtocol = "openai" | "openai_compatible" | "anthropic";
export type LlmReasoningProfile =
  | "none"
  | "request_patch"
  | "openai_reasoning_effort"
  | "anthropic_thinking"
  | "volcengine_thinking"
  | "vllm_enable_thinking"
  | "anthropic_budget_thinking"
  | "custom_json";

export type LlmUpdatePayload = Partial<{
  name: string;
  protocol: LlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  enabled: boolean;
  reasoning_profile: LlmReasoningProfile;
  reasoning_profile_json: string | null;
}>;

export type RepoSource = "git" | "local_dir";

export interface RepoUpdatePayload {
  name: string;
  source: RepoSource;
  url: string | null;
  local_path: string | null;
}
