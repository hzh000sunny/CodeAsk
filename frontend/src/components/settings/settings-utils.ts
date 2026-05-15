import type { LlmOpenCodeProviderProfile, LlmProtocol } from "./settings-types";

export const OPENCODE_PROVIDER_PROFILE_OPTIONS: Array<{
  value: LlmOpenCodeProviderProfile;
  label: string;
}> = [
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
];

export function safeEditableProtocol(protocol: string): LlmProtocol {
  if (protocol === "anthropic") {
    return "anthropic";
  }
  return "openai";
}

export function protocolLabel(protocol: string) {
  if (protocol === "anthropic") {
    return "Anthropic";
  }
  return "OpenAI";
}

export function opencodeProviderLabel(profile: string | null | undefined) {
  const value = profile || "default";
  return (
    OPENCODE_PROVIDER_PROFILE_OPTIONS.find((option) => option.value === value)?.label ??
    value
  );
}

export function safeOpenCodeProviderProfile(
  profile: string | null | undefined,
): LlmOpenCodeProviderProfile {
  const value = profile || "default";
  const option = OPENCODE_PROVIDER_PROFILE_OPTIONS.find((item) => item.value === value);
  return option?.value ?? "default";
}

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
