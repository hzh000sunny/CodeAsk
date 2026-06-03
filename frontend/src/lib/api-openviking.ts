import type {
  OpenVikingConfigTestResponse,
  OpenVikingEmbeddingApplyRequest,
  OpenVikingEmbeddingCandidatesResponse,
  OpenVikingEmbeddingResponse,
  OpenVikingEventsResponse,
  OpenVikingMutationCountResponse,
  OpenVikingOllamaSnippetResponse,
  OpenVikingOllamaVerifyResponse,
  OpenVikingStatusResponse,
  OpenVikingSyncJob,
  OpenVikingSyncJobsResponse,
  OpenVikingSyncJobsSummaryResponse,
  OpenVikingTuningApplyRequest,
  OpenVikingTuningApplyResponse,
  OpenVikingTuningPresetResponse,
  OpenVikingTuningResponse,
  OpenVikingVLMApplyRequest,
  OpenVikingVLMResponse,
} from "../types/api";
import { apiRequest } from "./api-client";

export function getOpenVikingStatus() {
  return apiRequest<OpenVikingStatusResponse>("/api/admin/openviking/status");
}

export function listOpenVikingSyncJobs(
  params: { page?: number; limit?: number; sourceType?: string; status?: string } = {},
) {
  const search = new URLSearchParams();
  if (params.status) {
    search.set("status", params.status);
  }
  if (params.sourceType) {
    search.set("source_type", params.sourceType);
  }
  if (params.page !== undefined) {
    search.set("page", String(params.page));
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  const query = search.toString();
  return apiRequest<OpenVikingSyncJobsResponse>(
    `/api/admin/openviking/sync_jobs${query ? `?${query}` : ""}`,
  );
}

export function getOpenVikingSyncJobsSummary() {
  return apiRequest<OpenVikingSyncJobsSummaryResponse>("/api/admin/openviking/sync_jobs/summary");
}

export function deleteOpenVikingSyncJob(jobId: string) {
  return apiRequest<{ deleted: true }>(`/api/admin/openviking/sync_jobs/${jobId}`, {
    method: "DELETE",
  });
}

export function listOpenVikingEvents(
  params: {
    beforeId?: number;
    eventType?: string;
    limit?: number;
    outcome?: string;
    page?: number;
    view?: "all" | "important";
  } = {},
) {
  const search = new URLSearchParams();
  if (params.eventType) {
    search.set("event_type", params.eventType);
  }
  if (params.outcome) {
    search.set("outcome", params.outcome);
  }
  if (params.view) {
    search.set("view", params.view);
  }
  if (params.beforeId) {
    search.set("before_id", String(params.beforeId));
  }
  if (params.limit) {
    search.set("limit", String(params.limit));
  }
  if (params.page) {
    search.set("page", String(params.page));
  }
  const query = search.toString();
  return apiRequest<OpenVikingEventsResponse>(
    `/api/admin/openviking/events${query ? `?${query}` : ""}`,
  );
}

export function getOpenVikingEmbedding() {
  return apiRequest<OpenVikingEmbeddingResponse>("/api/admin/openviking/embedding");
}

export function getOpenVikingTuning() {
  return apiRequest<OpenVikingTuningResponse>("/api/admin/openviking/tuning");
}

export function applyOpenVikingTuning(payload: OpenVikingTuningApplyRequest) {
  return apiRequest<OpenVikingTuningApplyResponse>("/api/admin/openviking/tuning", {
    method: "POST",
    body: payload,
  });
}

export function rollbackOpenVikingTuning(payload: { scope: string; key: string }) {
  return apiRequest<OpenVikingTuningApplyResponse>("/api/admin/openviking/tuning/rollback", {
    method: "POST",
    body: payload,
  });
}

export function applyOpenVikingTuningPreset(preset: string) {
  return apiRequest<OpenVikingTuningApplyResponse>("/api/admin/openviking/tuning/apply_preset", {
    method: "POST",
    body: { preset },
  });
}

export function getTuningPreset() {
  return apiRequest<OpenVikingTuningPresetResponse>("/api/admin/openviking/tuning/preset");
}

export function getTuningHistory(params: { scope?: string; key?: string } = {}) {
  const search = new URLSearchParams();
  if (params.scope) {
    search.set("scope", params.scope);
  }
  if (params.key) {
    search.set("key", params.key);
  }
  const query = search.toString();
  return apiRequest<{ items: unknown[] }>(
    `/api/admin/openviking/tuning/history${query ? `?${query}` : ""}`,
  );
}

export function getOllamaSnippet() {
  return apiRequest<OpenVikingOllamaSnippetResponse>(
    "/api/admin/openviking/tuning/ollama_snippet",
  );
}

export function verifyOllamaSettings() {
  return apiRequest<OpenVikingOllamaVerifyResponse>(
    "/api/admin/openviking/tuning/ollama_verify",
    { method: "POST" },
  );
}

export function listEmbeddingCandidates(baseUrl?: string) {
  const query = baseUrl ? `?base_url=${encodeURIComponent(baseUrl)}` : "";
  return apiRequest<OpenVikingEmbeddingCandidatesResponse>(
    `/api/admin/openviking/embedding/candidates${query}`,
  );
}

export function applyEmbeddingConfig(payload: OpenVikingEmbeddingApplyRequest) {
  return apiRequest<OpenVikingEmbeddingResponse>("/api/admin/openviking/embedding", {
    method: "POST",
    body: payload,
  });
}

export function testEmbeddingConfig(payload: OpenVikingEmbeddingApplyRequest) {
  return apiRequest<OpenVikingConfigTestResponse>("/api/admin/openviking/embedding/test", {
    method: "POST",
    body: payload,
  });
}

export function getOpenVikingVLM() {
  return apiRequest<OpenVikingVLMResponse>("/api/admin/openviking/vlm");
}

export function applyVLMConfig(payload: OpenVikingVLMApplyRequest) {
  return apiRequest<OpenVikingVLMResponse>("/api/admin/openviking/vlm", {
    method: "POST",
    body: payload,
  });
}

export function disableVLMConfig() {
  return apiRequest<OpenVikingVLMResponse>("/api/admin/openviking/vlm/disable", {
    method: "POST",
  });
}

export function testVLMConfig(payload: OpenVikingVLMApplyRequest) {
  return apiRequest<OpenVikingConfigTestResponse>("/api/admin/openviking/vlm/test", {
    method: "POST",
    body: payload,
  });
}

export function getVLMHistory() {
  return apiRequest<{ items: OpenVikingVLMResponse[] }>(
    "/api/admin/openviking/vlm/history",
  );
}

export function rebuildEmbedding() {
  return apiRequest<OpenVikingMutationCountResponse>("/api/admin/openviking/embedding/rebuild", {
    method: "POST",
  });
}

export function getEmbeddingHistory() {
  return apiRequest<{ items: OpenVikingEmbeddingResponse[] }>(
    "/api/admin/openviking/embedding/history",
  );
}

export function retrySyncJob(jobId: string) {
  return apiRequest<OpenVikingSyncJob>(`/api/admin/openviking/sync_jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export function retryFailedSyncJobs() {
  return apiRequest<OpenVikingMutationCountResponse>(
    "/api/admin/openviking/sync_jobs/retry_failed",
    { method: "POST" },
  );
}

export function resyncOpenViking(payload: { source_type?: string; feature_slug?: string } = {}) {
  return apiRequest<OpenVikingMutationCountResponse>("/api/admin/openviking/resync", {
    method: "POST",
    body: payload,
  });
}

export function rebuildOpenVikingIndex() {
  return apiRequest<OpenVikingMutationCountResponse>("/api/admin/openviking/rebuild_index", {
    method: "POST",
  });
}
