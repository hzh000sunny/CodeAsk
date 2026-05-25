import type {
  OpenVikingEmbeddingResponse,
  OpenVikingEventsResponse,
  OpenVikingStatusResponse,
  OpenVikingSyncJobsResponse,
  OpenVikingTuningResponse,
} from "../types/api";
import { apiRequest } from "./api-client";

export function getOpenVikingStatus() {
  return apiRequest<OpenVikingStatusResponse>("/api/admin/openviking/status");
}

export function listOpenVikingSyncJobs() {
  return apiRequest<OpenVikingSyncJobsResponse>("/api/admin/openviking/sync_jobs");
}

export function listOpenVikingEvents() {
  return apiRequest<OpenVikingEventsResponse>("/api/admin/openviking/events");
}

export function getOpenVikingEmbedding() {
  return apiRequest<OpenVikingEmbeddingResponse>("/api/admin/openviking/embedding");
}

export function getOpenVikingTuning() {
  return apiRequest<OpenVikingTuningResponse>("/api/admin/openviking/tuning");
}
