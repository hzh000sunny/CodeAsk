import { getSubjectId } from "./identity";
import type {
  AuditLogResponse,
  AttachmentResponse,
  AuthMeResponse,
  FeedbackAck,
  FeedbackVerdict,
  FrontendEventAck,
  DocumentRead,
  FeatureRead,
  LLMConfigResponse,
  RepoOut,
  ReportRead,
  SessionResponse,
  SkillResponse,
} from "../types/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(
      typeof detail === "string" ? detail : `API request failed with ${status}`,
    );
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type JsonBody = Record<string, unknown> | Array<unknown>;
type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | JsonBody | null;
};
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

export async function apiRequest<T>(
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Subject-Id", getSubjectId());

  let body = init.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(body);
  }

  const response = await fetch(path, {
    ...init,
    headers,
    body: body as BodyInit | null | undefined,
    credentials: "same-origin",
  });

  if (!response.ok) {
    const detail = await readResponse(response);
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await readResponse(response)) as T;
}

async function readResponse(response: Response) {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

export function getMe() {
  return apiRequest<AuthMeResponse>("/api/auth/me");
}

export function adminLogin(payload: { username: string; password: string }) {
  return apiRequest<AuthMeResponse>("/api/auth/admin/login", {
    method: "POST",
    body: payload,
  });
}

export function logout() {
  return apiRequest<void>("/api/auth/logout", {
    method: "POST",
  });
}

export function listSessions() {
  return apiRequest<SessionResponse[]>("/api/sessions");
}

export function createSession(title: string) {
  return apiRequest<SessionResponse>("/api/sessions", {
    method: "POST",
    body: { title },
  });
}

export function deleteSession(sessionId: string) {
  return apiRequest<void>(`/api/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export function updateSession(
  sessionId: string,
  payload: Partial<{ title: string; pinned: boolean }>,
) {
  return apiRequest<SessionResponse>(`/api/sessions/${sessionId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function bulkDeleteSessions(sessionIds: string[]) {
  return apiRequest<{ deleted_ids: string[] }>("/api/sessions/bulk-delete", {
    method: "POST",
    body: { session_ids: sessionIds },
  });
}

export function generateSessionReport(
  sessionId: string,
  payload: { feature_id: number; title: string },
) {
  return apiRequest<ReportRead>(`/api/sessions/${sessionId}/reports`, {
    method: "POST",
    body: {
      feature_id: payload.feature_id,
      title: payload.title,
    },
  });
}

export function postFeedback(payload: {
  session_turn_id: string;
  feedback: FeedbackVerdict;
  note?: string | null;
}) {
  return apiRequest<FeedbackAck>("/api/feedback", {
    method: "POST",
    body: payload,
  });
}

export function postFrontendEvent(payload: {
  event_type: string;
  session_id?: string | null;
  payload?: Record<string, unknown>;
}) {
  return apiRequest<FrontendEventAck>("/api/events", {
    method: "POST",
    body: {
      event_type: payload.event_type,
      session_id: payload.session_id ?? null,
      payload: payload.payload ?? {},
    },
  });
}

export function listAuditLog(entityType: string, entityId: string, limit = 50) {
  const params = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
    limit: String(limit),
  });
  return apiRequest<AuditLogResponse>(`/api/audit-log?${params.toString()}`);
}

export function uploadSessionAttachment(
  sessionId: string,
  file: File,
  kind: AttachmentResponse["kind"] = "log",
) {
  const body = new FormData();
  body.set("file", file);
  body.set("kind", kind);
  return apiRequest<AttachmentResponse>(
    `/api/sessions/${sessionId}/attachments`,
    {
      method: "POST",
      body,
    },
  );
}

export function listSessionAttachments(
  sessionId: string,
  signal?: AbortSignal,
) {
  return apiRequest<AttachmentResponse[]>(
    `/api/sessions/${sessionId}/attachments`,
    {
      signal,
    },
  );
}

export function renameSessionAttachment(
  sessionId: string,
  attachmentId: string,
  displayName: string,
) {
  return updateSessionAttachment(sessionId, attachmentId, {
    display_name: displayName,
  });
}

export function updateSessionAttachment(
  sessionId: string,
  attachmentId: string,
  payload: Partial<{ display_name: string; description: string | null }>,
) {
  return apiRequest<AttachmentResponse>(
    `/api/sessions/${sessionId}/attachments/${attachmentId}`,
    {
      method: "PATCH",
      body: payload,
    },
  );
}

export function deleteSessionAttachment(
  sessionId: string,
  attachmentId: string,
) {
  return apiRequest<void>(
    `/api/sessions/${sessionId}/attachments/${attachmentId}`,
    {
      method: "DELETE",
    },
  );
}

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

export function listRepos() {
  return apiRequest<{ repos: RepoOut[] }>("/api/repos").then(
    (payload) => payload.repos,
  );
}

export function listFeatureRepos(featureId: number) {
  return apiRequest<{ repos: RepoOut[] }>(
    `/api/features/${featureId}/repos`,
  ).then((payload) => payload.repos);
}

export function linkFeatureRepo(featureId: number, repoId: string) {
  return apiRequest<RepoOut>(`/api/features/${featureId}/repos/${repoId}`, {
    method: "POST",
  });
}

export function unlinkFeatureRepo(featureId: number, repoId: string) {
  return apiRequest<void>(`/api/features/${featureId}/repos/${repoId}`, {
    method: "DELETE",
  });
}

export function createRepo(payload: {
  name: string;
  source: "git" | "local_dir";
  url?: string | null;
  local_path?: string | null;
}) {
  return apiRequest<RepoOut>("/api/repos", {
    method: "POST",
    body: payload,
  });
}

export function deleteRepo(repoId: string) {
  return apiRequest<void>(`/api/repos/${repoId}`, {
    method: "DELETE",
  });
}

export function refreshRepo(repoId: string) {
  return apiRequest<RepoOut>(`/api/repos/${repoId}/refresh`, {
    method: "POST",
  });
}

export function listSkills() {
  return apiRequest<SkillResponse[]>("/api/skills");
}

export function createSkill(payload: {
  name: string;
  scope: "global" | "feature";
  feature_id?: number | null;
  prompt_template: string;
}) {
  return apiRequest<SkillResponse>("/api/skills", {
    method: "POST",
    body: payload,
  });
}

export function updateSkill(
  skillId: string,
  payload: Partial<{ name: string; prompt_template: string }>,
) {
  return apiRequest<SkillResponse>(`/api/skills/${skillId}`, {
    method: "PATCH",
    body: payload,
  });
}

export function deleteSkill(skillId: string) {
  return apiRequest<void>(`/api/skills/${skillId}`, {
    method: "DELETE",
  });
}

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
