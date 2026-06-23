const SUBJECT_KEY = "codeask.subject_id";
const NICKNAME_KEY = "codeask.nickname";
const GUEST_LLM_CONFIG_KEY = "codeask.guest_llm_config";

export type GuestLlmConfigMode = "catalog" | "custom";
export type GuestLlmReasoningProfile =
  | "none"
  | "volcengine_thinking"
  | "vllm_enable_thinking"
  | "anthropic_budget_thinking"
  | "custom_json";

export interface GuestLlmConfig {
  name: string;
  mode: GuestLlmConfigMode;
  provider_id: string;
  base_url: string | null;
  api_key: string;
  headers: Record<string, string> | null;
  model_name: string;
  reasoning_profile: GuestLlmReasoningProfile;
  reasoning_profile_json: string | null;
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
    mode: data.mode === "custom" ? "custom" : "catalog",
    provider_id: stringValue(data.provider_id, ""),
    base_url: nullableStringValue(data.base_url),
    api_key: stringValue(data.api_key, ""),
    headers: headersValue(data.headers),
    model_name: stringValue(data.model_name, ""),
    reasoning_profile: reasoningProfileValue(data.reasoning_profile),
    reasoning_profile_json: nullableStringValue(data.reasoning_profile_json),
  };
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function nullableStringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function headersValue(value: unknown): Record<string, string> | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([key, val]) => key.trim() && typeof val === "string")
    .map(([key, val]) => [key.trim(), val as string] as const);
  return entries.length > 0 ? Object.fromEntries(entries) : null;
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
