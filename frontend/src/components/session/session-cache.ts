import type { QueryClient } from "@tanstack/react-query";

import type { AttachmentResponse, SessionResponse } from "../../types/api";

export function sessionAttachmentsQueryKey(sessionId: string) {
  return ["session-attachments", sessionId] as const;
}

export function sessionTurnsQueryKey(sessionId: string) {
  return ["session-turns", sessionId] as const;
}

export function sessionTracesQueryKey(sessionId: string) {
  return ["session-traces", sessionId] as const;
}

export function upsertAttachment(
  queryClient: QueryClient,
  attachment: AttachmentResponse,
) {
  queryClient.setQueryData<AttachmentResponse[]>(
    sessionAttachmentsQueryKey(attachment.session_id),
    (current = []) => {
      const next = current.filter((item) => item.id !== attachment.id);
      return [...next, attachment].sort(
        (left, right) =>
          new Date(left.created_at).getTime() -
            new Date(right.created_at).getTime() ||
          left.id.localeCompare(right.id),
      );
    },
  );
}

export function upsertSession(queryClient: QueryClient, session: SessionResponse) {
  queryClient.setQueryData<SessionResponse[]>(["sessions"], (current = []) => {
    const next = current.filter((item) => item.id !== session.id);
    return [session, ...next];
  });
}
