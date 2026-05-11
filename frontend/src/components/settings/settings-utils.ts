import type { LlmProtocol } from "./settings-types";

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
