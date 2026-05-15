const SUBJECT_KEY = "codeask.subject_id";
const NICKNAME_KEY = "codeask.nickname";
const GUEST_LLM_CONFIG_KEY = "codeask.guest_llm_config";

export type GuestLlmProtocol = "openai" | "anthropic";
export type GuestOpenCodeProviderProfile =
  | "default"
  | "openai-native"
  | "openai-compatible"
  | "anthropic-native"
  | "anthropic-compatible-bearer"
  | "anthropic-compatible-v1-bearer"
  | "openrouter";
export type GuestLlmReasoningProfile =
  | "none"
  | "volcengine_thinking"
  | "vllm_enable_thinking"
  | "anthropic_budget_thinking"
  | "custom_json";

export interface GuestLlmConfig {
  name: string;
  protocol: GuestLlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  max_tokens: number;
  temperature: number;
  reasoning_profile: GuestLlmReasoningProfile;
  reasoning_profile_json: string | null;
  opencode_provider_profile: GuestOpenCodeProviderProfile;
}

function createClientId() {
  if (globalThis.crypto?.randomUUID) {
    return `client_${globalThis.crypto.randomUUID().replaceAll("-", "").slice(0, 18)}`;
  }
  return `client_${Math.random().toString(36).slice(2, 14)}`;
}

export function getSubjectId() {
  const existing = localStorage.getItem(SUBJECT_KEY);
  if (existing) {
    return existing;
  }
  const created = createClientId();
  localStorage.setItem(SUBJECT_KEY, created);
  return created;
}

export function getNickname() {
  return localStorage.getItem(NICKNAME_KEY) ?? "";
}

export function setNickname(nickname: string) {
  const trimmed = nickname.trim();
  if (trimmed) {
    localStorage.setItem(NICKNAME_KEY, trimmed);
  } else {
    localStorage.removeItem(NICKNAME_KEY);
  }
}

export function getGuestLlmConfig(): GuestLlmConfig | null {
  const raw = localStorage.getItem(GUEST_LLM_CONFIG_KEY);
  if (!raw) {
    return null;
  }
  try {
    return sanitizeGuestLlmConfig(JSON.parse(raw));
  } catch {
    localStorage.removeItem(GUEST_LLM_CONFIG_KEY);
    return null;
  }
}

export function setGuestLlmConfig(config: GuestLlmConfig) {
  localStorage.setItem(
    GUEST_LLM_CONFIG_KEY,
    JSON.stringify(sanitizeGuestLlmConfig(config)),
  );
}

export function clearGuestLlmConfig() {
  localStorage.removeItem(GUEST_LLM_CONFIG_KEY);
}

function sanitizeGuestLlmConfig(value: unknown): GuestLlmConfig {
  const data = value && typeof value === "object" ? (value as Partial<GuestLlmConfig>) : {};
  return {
    name: stringValue(data.name, "访客 LLM"),
    protocol: protocolValue(data.protocol),
    base_url: nullableStringValue(data.base_url),
    api_key: stringValue(data.api_key, ""),
    model_name: stringValue(data.model_name, ""),
    max_tokens: numberValue(data.max_tokens, 4096),
    temperature: numberValue(data.temperature, 0),
    reasoning_profile: reasoningProfileValue(data.reasoning_profile),
    reasoning_profile_json: nullableStringValue(data.reasoning_profile_json),
    opencode_provider_profile: opencodeProviderProfileValue(
      data.opencode_provider_profile,
    ),
  };
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function nullableStringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function protocolValue(value: unknown): GuestLlmProtocol {
  return value === "anthropic" ? "anthropic" : "openai";
}

function reasoningProfileValue(value: unknown): GuestLlmReasoningProfile {
  const allowed: GuestLlmReasoningProfile[] = [
    "none",
    "volcengine_thinking",
    "vllm_enable_thinking",
    "anthropic_budget_thinking",
    "custom_json",
  ];
  return allowed.includes(value as GuestLlmReasoningProfile)
    ? (value as GuestLlmReasoningProfile)
    : "none";
}

function opencodeProviderProfileValue(value: unknown): GuestOpenCodeProviderProfile {
  const allowed: GuestOpenCodeProviderProfile[] = [
    "default",
    "openai-native",
    "openai-compatible",
    "anthropic-native",
    "anthropic-compatible-bearer",
    "anthropic-compatible-v1-bearer",
    "openrouter",
  ];
  return allowed.includes(value as GuestOpenCodeProviderProfile)
    ? (value as GuestOpenCodeProviderProfile)
    : "default";
}
