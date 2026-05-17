import type {
  LlmAgentRuntimeProfile,
  LlmProtocol,
  LlmRuntimeProfileOption,
} from "./settings-types";

export const FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS: LlmRuntimeProfileOption[] = [
  { value: "default", label: "Default" },
  { value: "openai-native", label: "OpenAI Native" },
  { value: "openai-compatible", label: "OpenAI Compatible" },
  { value: "anthropic-native", label: "Anthropic Native" },
  { value: "anthropic-compatible-bearer", label: "Anthropic Compatible Bearer" },
  {
    value: "anthropic-compatible-v1-bearer",
    label: "Anthropic Compatible /v1 Bearer",
  },
  { value: "openrouter", label: "OpenRouter" },
].map((option) => ({ ...option, description: "" }));

export function safeEditableProtocol(protocol: string): LlmProtocol {
  if (protocol === "anthropic") {
    return "anthropic";
  }
  if (protocol === "openai_compatible") {
    return "openai_compatible";
  }
  return "openai";
}

export function protocolLabel(protocol: string) {
  if (protocol === "anthropic") {
    return "Anthropic";
  }
  if (protocol === "openai_compatible") {
    return "OpenAI Compatible";
  }
  return "OpenAI";
}

export function agentRuntimeProfileLabel(
  profile: string | null | undefined,
  options: LlmRuntimeProfileOption[] = FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS,
) {
  const value = profile || "default";
  return options.find((option) => option.value === value)?.label ?? value;
}

export function opencodeProviderLabel(profile: string | null | undefined) {
  return agentRuntimeProfileLabel(profile);
}

export function safeAgentRuntimeProfile(
  profile: string | null | undefined,
  options: LlmRuntimeProfileOption[] = FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS,
): LlmAgentRuntimeProfile {
  const value = profile || "default";
  const option = options.find((item) => item.value === value);
  return option?.value ?? "default";
}

export const safeOpenCodeProviderProfile = safeAgentRuntimeProfile;

export function messageFromApiError(error: unknown) {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof detail === "object" && detail !== null && "detail" in detail) {
      const nested = (detail as { detail?: unknown }).detail;
      if (typeof nested === "string") {
        return nested;
      }
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败";
}
