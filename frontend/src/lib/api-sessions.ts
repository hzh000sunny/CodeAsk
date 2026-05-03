import type {
  AgentTraceResponse,
  AttachmentResponse,
  FeedbackAck,
  FeedbackVerdict,
  FrontendEventAck,
  ReportRead,
  SessionResponse,
  SessionTurnResponse,
} from "../types/api";
import { apiRequest } from "./api-client";

export function listSessions() {
  return apiRequest<SessionResponse[]>("/api/sessions");
}

export function listSessionTurns(sessionId: string, signal?: AbortSignal) {
  return apiRequest<SessionTurnResponse[]>(`/api/sessions/${sessionId}/turns`, {
    signal,
  });
}

export function listSessionTraces(sessionId: string, signal?: AbortSignal) {
  return apiRequest<AgentTraceResponse[]>(`/api/sessions/${sessionId}/traces`, {
    signal,
  });
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
