import type { DocumentRead, FeatureRead, ReportRead } from "../types/api";
import { apiRequest } from "./api-client";

export function listFeatures() {
  return apiRequest<FeatureRead[]>("/api/features");
}

export function createFeature(payload: { name: string; description?: string }) {
  return apiRequest<FeatureRead>("/api/features", {
    method: "POST",
    body: payload,
  });
}

export function updateFeature(
  id: number,
  payload: { name?: string; description?: string },
) {
  return apiRequest<FeatureRead>(`/api/features/${id}`, {
    method: "PUT",
    body: payload,
  });
}

export function deleteFeature(id: number) {
  return apiRequest<void>(`/api/features/${id}`, {
    method: "DELETE",
  });
}

export function listDocuments(featureId?: number) {
  const query = featureId ? `?feature_id=${featureId}` : "";
  return apiRequest<DocumentRead[]>(`/api/documents${query}`);
}

export function uploadDocument(payload: {
  feature_id: number;
  file: File;
  title?: string;
  tags?: string;
}) {
  const body = new FormData();
  body.set("feature_id", String(payload.feature_id));
  body.set("file", payload.file);
  if (payload.title) {
    body.set("title", payload.title);
  }
  if (payload.tags) {
    body.set("tags", payload.tags);
  }
  return apiRequest<DocumentRead>("/api/documents", {
    method: "POST",
    body,
  });
}

export function deleteDocument(documentId: number) {
  return apiRequest<void>(`/api/documents/${documentId}`, {
    method: "DELETE",
  });
}

export function listReports(featureId?: number) {
  const query = featureId ? `?feature_id=${featureId}` : "";
  return apiRequest<ReportRead[]>(`/api/reports${query}`);
}

export function createReport(payload: {
  feature_id?: number | null;
  title: string;
  body_markdown: string;
  metadata?: Record<string, unknown>;
}) {
  return apiRequest<ReportRead>("/api/reports", {
    method: "POST",
    body: {
      feature_id: payload.feature_id ?? null,
      title: payload.title,
      body_markdown: payload.body_markdown,
      metadata: payload.metadata ?? {},
    },
  });
}

export function verifyReport(reportId: number) {
  return apiRequest<ReportRead>(`/api/reports/${reportId}/verify`, {
    method: "POST",
  });
}

export function rejectReport(reportId: number) {
  return apiRequest<ReportRead>(`/api/reports/${reportId}/reject`, {
    method: "POST",
  });
}

export function unverifyReport(reportId: number) {
  return apiRequest<ReportRead>(`/api/reports/${reportId}/unverify`, {
    method: "POST",
  });
}

export function updateReport(
  reportId: number,
  payload: Partial<{
    title: string;
    body_markdown: string;
    metadata: Record<string, unknown>;
  }>,
) {
  return apiRequest<ReportRead>(`/api/reports/${reportId}`, {
    method: "PUT",
    body: payload,
  });
}

export function deleteReport(reportId: number) {
  return apiRequest<void>(`/api/reports/${reportId}`, {
    method: "DELETE",
  });
}
