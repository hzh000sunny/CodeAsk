import type { LlmConfigMode, LlmProviderOption } from "./settings-types";

export function modeLabel(mode: LlmConfigMode | string) {
  return mode === "custom" ? "自建网关" : "目录 provider";
}

/** opencode 自定义 provider 的 slug 规则（dialog-custom-provider-form.ts）。 */
export function sanitizeProviderSlug(value: string) {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\-_]/g, "-");
  return cleaned || "custom";
}

/** 目录条目里把 provider_id 翻成展示名，找不到则回落到 id。 */
export function providerLabel(
  providerId: string,
  options: LlmProviderOption[] = [],
) {
  return options.find((option) => option.id === providerId)?.name ?? providerId;
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
