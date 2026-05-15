import type { LLMConfigResponse, LLMConfigTestResponse } from "../types/api";
import { apiRequest } from "./api-client";

type LlmProtocol = "openai" | "openai_compatible" | "anthropic";
type LlmOpenCodeProviderProfile =
  | "default"
  | "openai-native"
  | "openai-compatible"
  | "anthropic-native"
  | "anthropic-compatible-bearer"
  | "anthropic-compatible-v1-bearer"
  | "openrouter";
type LlmReasoningProfile =
  | "none"
  | "request_patch"
  | "openai_reasoning_effort"
  | "anthropic_thinking"
  | "volcengine_thinking"
  | "vllm_enable_thinking"
  | "anthropic_budget_thinking"
  | "custom_json";
type LlmCreatePayload = {
  name: string;
  protocol: LlmProtocol;
  base_url?: string | null;
  api_key: string;
  model_name: string;
  enabled?: boolean;
  reasoning_profile?: LlmReasoningProfile;
  reasoning_profile_json?: string | null;
  opencode_provider_profile?: LlmOpenCodeProviderProfile;
  opencode_provider_status?: "unknown" | "ok" | "failed";
  opencode_provider_tested_at?: string | null;
  opencode_provider_error?: string | null;
  opencode_provider_test_result_json?: unknown | null;
};
type LlmUpdatePayload = Partial<
  Omit<LlmCreatePayload, "api_key"> & {
    api_key: string;
    opencode_provider_status: "unknown" | "ok" | "failed";
    opencode_provider_tested_at: string | null;
    opencode_provider_error: string | null;
    opencode_provider_test_result_json: unknown | null;
  }
>;

export function listUserLlmConfigs() {
  return apiRequest<LLMConfigResponse[]>("/api/me/llm-configs");
}

export function createUserLlmConfig(payload: LlmCreatePayload) {
  return apiRequest<LLMConfigResponse>("/api/me/llm-configs", {
    method: "POST",
    body: payload,
  });
}

export function updateUserLlmConfig(id: string, payload: LlmUpdatePayload) {
  return apiRequest<LLMConfigResponse>(`/api/me/llm-configs/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteUserLlmConfig(id: string) {
  return apiRequest<void>(`/api/me/llm-configs/${id}`, {
    method: "DELETE",
  });
}

export function testUserLlmConfig(id: string) {
  return apiRequest<LLMConfigTestResponse>(`/api/me/llm-configs/${id}/test`, {
    method: "POST",
  });
}

export function testUserLlmConfigDraft(payload: LlmCreatePayload) {
  return apiRequest<LLMConfigTestResponse>("/api/me/llm-configs/test-draft", {
    method: "POST",
    body: payload,
  });
}

export function testUserLlmConfigUpdateDraft(id: string, payload: LlmUpdatePayload) {
  return apiRequest<LLMConfigTestResponse>(`/api/me/llm-configs/${id}/test-draft`, {
    method: "POST",
    body: payload,
  });
}

export function listAdminLlmConfigs() {
  return apiRequest<LLMConfigResponse[]>("/api/admin/llm-configs");
}

export function createAdminLlmConfig(payload: LlmCreatePayload) {
  return apiRequest<LLMConfigResponse>("/api/admin/llm-configs", {
    method: "POST",
    body: payload,
  });
}

export function updateAdminLlmConfig(id: string, payload: LlmUpdatePayload) {
  return apiRequest<LLMConfigResponse>(`/api/admin/llm-configs/${id}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteAdminLlmConfig(id: string) {
  return apiRequest<void>(`/api/admin/llm-configs/${id}`, {
    method: "DELETE",
  });
}

export function testAdminLlmConfig(id: string) {
  return apiRequest<LLMConfigTestResponse>(`/api/admin/llm-configs/${id}/test`, {
    method: "POST",
  });
}

export function testAdminLlmConfigDraft(payload: LlmCreatePayload) {
  return apiRequest<LLMConfigTestResponse>("/api/admin/llm-configs/test-draft", {
    method: "POST",
    body: payload,
  });
}

export function testAdminLlmConfigUpdateDraft(id: string, payload: LlmUpdatePayload) {
  return apiRequest<LLMConfigTestResponse>(
    `/api/admin/llm-configs/${id}/test-draft`,
    {
      method: "POST",
      body: payload,
    },
  );
}
