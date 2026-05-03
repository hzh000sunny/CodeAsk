import type { LLMConfigResponse } from "../types/api";
import { apiRequest } from "./api-client";

type LlmProtocol = "openai" | "anthropic";
type LlmCreatePayload = {
  name: string;
  protocol: LlmProtocol;
  base_url?: string | null;
  api_key: string;
  model_name: string;
  enabled?: boolean;
};
type LlmUpdatePayload = Partial<
  Omit<LlmCreatePayload, "api_key"> & {
    api_key: string;
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
