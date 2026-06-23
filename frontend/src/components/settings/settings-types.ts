export type LlmScope = "user" | "global";

/** opencode 的两条 provider 流程：目录解析 vs 自建网关 openai-compatible。 */
export type LlmConfigMode = "catalog" | "custom";

/** models.dev 目录条目（GET /api/llm-providers）。 */
export interface LlmProviderOption {
  id: string;
  name: string;
}

export type LlmHeaders = Record<string, string>;

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
  mode: LlmConfigMode;
  provider_id: string;
  base_url: string | null;
  api_key: string;
  headers: LlmHeaders | null;
  model_name: string;
  enabled: boolean;
  reasoning_profile: LlmReasoningProfile;
  reasoning_profile_json: string | null;
  opencode_provider_status: "unknown" | "ok" | "failed";
  opencode_provider_tested_at: string | null;
  opencode_provider_error: string | null;
  opencode_provider_test_result_json: unknown | null;
}>;

export type RepoSource = "git" | "local_dir";

export interface RepoUpdatePayload {
  name: string;
  source: RepoSource;
  url: string | null;
  local_path: string | null;
}
