import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createSession,
  deleteSessionAttachment,
  listSessionAttachments,
  renameSessionAttachment,
  updateSessionAttachment,
  uploadSessionAttachment,
} from "../../lib/api";
import type { AttachmentResponse, SessionResponse } from "../../types/api";
import {
  sessionAttachmentsQueryKey,
  upsertAttachment,
} from "./session-cache";
import { messageFromError } from "./session-model";

export function useSessionAttachments({
  onSessionCreated,
  rememberSession,
  selected,
  selectedSessionId,
  showActionNotice,
}: {
  onSessionCreated: (sessionId: string) => void;
  rememberSession: (session: SessionResponse) => void;
  selected: SessionResponse | null;
  selectedSessionId: string;
  showActionNotice: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const { data: attachments = [], isFetching: isFetchingAttachments } =
    useQuery({
      queryKey: sessionAttachmentsQueryKey(selectedSessionId),
      queryFn: ({ signal }) =>
        listSessionAttachments(selectedSessionId, signal),
      enabled: Boolean(selectedSessionId),
      staleTime: 30_000,
    });

  const renameAttachmentMutation = useMutation({
    mutationFn: ({
      attachmentId,
      displayName,
      sessionId,
    }: {
      attachmentId: string;
      displayName: string;
      sessionId: string;
    }) => renameSessionAttachment(sessionId, attachmentId, displayName),
    onSuccess: (attachment) => {
      showActionNotice(`已重命名为 ${attachment.display_name}`);
      upsertAttachment(queryClient, attachment);
    },
    onError: (error) => {
      showActionNotice(`重命名会话数据失败：${messageFromError(error)}`);
    },
  });
  const describeAttachmentMutation = useMutation({
    mutationFn: ({
      attachmentId,
      description,
      sessionId,
    }: {
      attachmentId: string;
      description: string | null;
      sessionId: string;
    }) => updateSessionAttachment(sessionId, attachmentId, { description }),
    onSuccess: (attachment) => {
      showActionNotice("已更新用途说明");
      upsertAttachment(queryClient, attachment);
    },
    onError: (error) => {
      showActionNotice(`更新用途说明失败：${messageFromError(error)}`);
    },
  });
  const deleteAttachmentMutation = useMutation({
    mutationFn: ({
      attachmentId,
      sessionId,
    }: {
      attachmentId: string;
      sessionId: string;
      displayName: string;
    }) => deleteSessionAttachment(sessionId, attachmentId),
    onSuccess: (_unused, variables) => {
      showActionNotice(`已删除 ${variables.displayName}`);
      queryClient.setQueryData<AttachmentResponse[]>(
        sessionAttachmentsQueryKey(variables.sessionId),
        (current = []) =>
          current.filter(
            (attachment) => attachment.id !== variables.attachmentId,
          ),
      );
    },
    onError: (error) => {
      showActionNotice(`删除会话数据失败：${messageFromError(error)}`);
    },
  });

  async function uploadLog(file: File | undefined) {
    if (!file) {
      return;
    }
    setUploadStatus("正在上传日志");
    try {
      let target = selected;
      if (!target) {
        target = await createSession(
          file.name.trim().slice(0, 28) || "新的研发会话",
        );
        onSessionCreated(target.id);
        rememberSession(target);
      }
      const uploaded = await uploadSessionAttachment(target.id, file, "log");
      await queryClient.cancelQueries({
        queryKey: sessionAttachmentsQueryKey(target.id),
      });
      upsertAttachment(queryClient, uploaded);
      setUploadStatus(`已上传 ${uploaded.display_name}`);
    } catch (error) {
      setUploadStatus(messageFromError(error));
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  function renameAttachment(attachment: AttachmentResponse) {
    const next = window.prompt("重命名会话数据", attachment.display_name);
    const displayName = next?.trim();
    if (!displayName || displayName === attachment.display_name) {
      return;
    }
    renameAttachmentMutation.mutate({
      attachmentId: attachment.id,
      displayName,
      sessionId: attachment.session_id,
    });
  }

  function deleteAttachment(attachment: AttachmentResponse) {
    if (!window.confirm(`确认删除“${attachment.display_name}”？`)) {
      return;
    }
    deleteAttachmentMutation.mutate({
      attachmentId: attachment.id,
      displayName: attachment.display_name,
      sessionId: attachment.session_id,
    });
  }

  function describeAttachment(attachment: AttachmentResponse) {
    const next = window.prompt("编辑用途说明", attachment.description ?? "");
    if (next === null) {
      return;
    }
    describeAttachmentMutation.mutate({
      attachmentId: attachment.id,
      description: next.trim() || null,
      sessionId: attachment.session_id,
    });
  }

  return {
    attachments,
    deleteAttachment,
    describeAttachment,
    fileInputRef,
    isFetchingAttachments,
    renameAttachment,
    uploadLog,
    uploadStatus,
  };
}
