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
import type { AttachmentDialog } from "./SessionAttachmentDialogs";
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
  showActionNotice: (message: string, tone?: "success" | "error") => void;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [attachmentDialog, setAttachmentDialog] =
    useState<AttachmentDialog | null>(null);
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
      showActionNotice(`重命名会话数据失败：${messageFromError(error)}`, "error");
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
      showActionNotice(`更新用途说明失败：${messageFromError(error)}`, "error");
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
      showActionNotice(`删除会话数据失败：${messageFromError(error)}`, "error");
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
        await queryClient.cancelQueries({ queryKey: ["sessions"] });
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
      await queryClient.invalidateQueries({
        queryKey: sessionAttachmentsQueryKey(target.id),
      });
      setUploadStatus(`已上传 ${uploaded.display_name}`);
    } catch (error) {
      const message = messageFromError(error);
      setUploadStatus("");
      showActionNotice(`上传日志失败：${message}`, "error");
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  function renameAttachment(attachment: AttachmentResponse) {
    setAttachmentDialog({ mode: "rename", attachment });
  }

  function deleteAttachment(attachment: AttachmentResponse) {
    setAttachmentDialog({ mode: "delete", attachment });
  }

  function describeAttachment(attachment: AttachmentResponse) {
    setAttachmentDialog({ mode: "describe", attachment });
  }

  function closeAttachmentDialog() {
    if (
      renameAttachmentMutation.isPending ||
      describeAttachmentMutation.isPending ||
      deleteAttachmentMutation.isPending
    ) {
      return;
    }
    setAttachmentDialog(null);
  }

  function submitRenameAttachment(displayName: string) {
    if (attachmentDialog?.mode !== "rename") {
      return;
    }
    const { attachment } = attachmentDialog;
    const next = displayName.trim();
    if (!next || next === attachment.display_name) {
      setAttachmentDialog(null);
      return;
    }
    renameAttachmentMutation.mutate(
      {
        attachmentId: attachment.id,
        displayName: next,
        sessionId: attachment.session_id,
      },
      { onSuccess: () => setAttachmentDialog(null) },
    );
  }

  function submitDescribeAttachment(description: string) {
    if (attachmentDialog?.mode !== "describe") {
      return;
    }
    const { attachment } = attachmentDialog;
    describeAttachmentMutation.mutate(
      {
        attachmentId: attachment.id,
        description: description.trim() || null,
        sessionId: attachment.session_id,
      },
      { onSuccess: () => setAttachmentDialog(null) },
    );
  }

  function submitDeleteAttachment() {
    if (attachmentDialog?.mode !== "delete") {
      return;
    }
    const { attachment } = attachmentDialog;
    deleteAttachmentMutation.mutate(
      {
        attachmentId: attachment.id,
        displayName: attachment.display_name,
        sessionId: attachment.session_id,
      },
      { onSuccess: () => setAttachmentDialog(null) },
    );
  }

  return {
    attachmentDialog,
    attachmentDialogPending:
      renameAttachmentMutation.isPending ||
      describeAttachmentMutation.isPending ||
      deleteAttachmentMutation.isPending,
    attachments,
    clearUploadStatus: () => setUploadStatus(""),
    closeAttachmentDialog,
    deleteAttachment,
    describeAttachment,
    fileInputRef,
    isFetchingAttachments,
    renameAttachment,
    submitDescribeAttachment,
    submitDeleteAttachment,
    submitRenameAttachment,
    uploadLog,
    uploadStatus,
  };
}
