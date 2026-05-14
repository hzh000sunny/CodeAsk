import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bulkDeleteSessions,
  createSession,
  deleteSession,
  getMe,
  getSystemSettings,
  listFeatures,
  listSessions,
  listSessionTraces,
  listSessionTurns,
  updateSession,
} from "../../lib/api";
import type {
  AgentTraceResponse,
  SessionResponse,
  SessionTurnResponse,
} from "../../types/api";
import { InvestigationPanel } from "./InvestigationPanel";
import { SessionConversationPanel } from "./SessionConversationPanel";
import { SessionListPanel } from "./SessionListPanel";
import { SessionWorkspaceDialogs } from "./SessionWorkspaceDialogs";
import {
  sessionTracesQueryKey,
  sessionListQueryKey,
  sessionTurnsQueryKey,
  upsertSession,
} from "./session-cache";
import {
  createInitialStages,
  messageFromError,
  type ConversationMessage,
  type RuntimeInsight,
  type RuntimeSessionState,
} from "./session-model";
import { useSessionAttachments } from "./useSessionAttachments";
import { useSessionFeedback } from "./useSessionFeedback";
import { useSessionHistoryRestore } from "./useSessionHistoryRestore";
import { useSessionMessageStream } from "./useSessionMessageStream";
import { useSessionNotices } from "./useSessionNotices";
import { useSessionReport } from "./useSessionReport";
import { useSessionWikiPromotion } from "./useSessionWikiPromotion";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface SessionWorkspaceProps {
  routeSelectedSessionId?: string | null;
  onSelectedSessionChange?: (sessionId: string | null) => void;
  onOpenReport?: (target: ReportTarget) => void;
  onOpenWiki?: (target: { featureId: number; nodeId: number }) => void;
}

const EMPTY_SESSION_TURNS: SessionTurnResponse[] = [];
const EMPTY_SESSION_TRACES: AgentTraceResponse[] = [];

export function SessionWorkspace({
  routeSelectedSessionId = null,
  onSelectedSessionChange,
  onOpenReport,
  onOpenWiki,
}: SessionWorkspaceProps) {
  const queryClient = useQueryClient();
  const appliedHistoryKeyRef = useRef<string | null>(null);
  const messagesSessionIdRef = useRef<string | null>(null);
  const previousSubjectQueryKeyRef = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeStreamingSessionId, setActiveStreamingSessionId] =
    useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [insights, setInsights] = useState<RuntimeInsight[]>([]);
  const [runtimeState, setRuntimeState] = useState<RuntimeSessionState | null>(null);
  const [stages, setStages] = useState(createInitialStages);
  const [selectedId, setSelectedId] = useState<string | null>(routeSelectedSessionId);
  const [rememberedSelectedSession, setRememberedSelectedSession] =
    useState<SessionResponse | null>(null);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [deletedSessionIds, setDeletedSessionIds] = useState<string[]>([]);
  const [deleteCandidate, setDeleteCandidate] =
    useState<SessionResponse | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [menuSessionId, setMenuSessionId] = useState<string | null>(null);
  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelectedIds, setBulkSelectedIds] = useState<string[]>([]);
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [detectedFeatureIds, setDetectedFeatureIds] = useState<number[]>([]);
  const { data: me } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
  });
  const subjectQueryKey = me
    ? `${me.authenticated ? "auth" : "anon"}:${me.subject_id}`
    : "pending";
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: sessionListQueryKey(subjectQueryKey),
    queryFn: ({ signal }) => listSessions(signal),
  });
  const { data: features = [] } = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const createMutation = useMutation({
    mutationFn: async () => {
      await queryClient.cancelQueries({ queryKey: ["sessions"] });
      return createSession("新的研发会话");
    },
    onSuccess: (session) => {
      setRuntimeState(null);
      setSelectedId(session.id);
      onSelectedSessionChange?.(session.id);
      rememberSession(session);
    },
  });
  function resetActiveSessionState() {
    setSelectedId(null);
    setRememberedSelectedSession(null);
    setMessages([]);
    messagesSessionIdRef.current = null;
    appliedHistoryKeyRef.current = null;
    setInsights([]);
    setRuntimeState(null);
    setStages(createInitialStages());
    setDetectedFeatureIds([]);
  }

  useEffect(() => {
    setSelectedId(routeSelectedSessionId);
  }, [routeSelectedSessionId]);

  function selectSession(sessionId: string | null) {
    if (sessionId !== selectedId) {
      setRuntimeState(null);
    }
    setSelectedId(sessionId);
    onSelectedSessionChange?.(sessionId);
  }

  useEffect(() => {
    const previousSubjectQueryKey = previousSubjectQueryKeyRef.current;
    previousSubjectQueryKeyRef.current = subjectQueryKey;
    if (
      previousSubjectQueryKey === null ||
      previousSubjectQueryKey === subjectQueryKey
    ) {
      return;
    }
    if (previousSubjectQueryKey === "pending") {
      const pendingSessions = queryClient.getQueryData<SessionResponse[]>(
        sessionListQueryKey(previousSubjectQueryKey),
      );
      if (pendingSessions?.length) {
        void queryClient.cancelQueries({
          queryKey: sessionListQueryKey(subjectQueryKey),
        });
        queryClient.setQueryData(
          sessionListQueryKey(subjectQueryKey),
          pendingSessions,
        );
      }
      return;
    }
    resetActiveSessionState();
    setDeletedSessionIds([]);
    setBulkSelectedIds([]);
    setBulkMode(false);
    setConfirmBulkDelete(false);
    setDeleteCandidate(null);
    setDeleteError("");
    setMenuSessionId(null);
  }, [queryClient, subjectQueryKey]);

  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: (_unused, sessionId) => {
      const activeSessionId = selected?.id ?? selectedId;
      setDeletedSessionIds((current) => [...new Set([...current, sessionId])]);
      setDeleteCandidate(null);
      setDeleteError("");
      if (activeSessionId === sessionId) {
        resetActiveSessionState();
        onSelectedSessionChange?.(null);
      }
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => {
      const message = `删除会话失败：${messageFromError(error)}`;
      setDeleteError(message);
      showActionNotice(message, "error");
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({
      sessionId,
      payload,
    }: {
      sessionId: string;
      payload: Partial<{ title: string; pinned: boolean }>;
    }) => updateSession(sessionId, payload),
    onSuccess: () => {
      setMenuSessionId(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
  const bulkDeleteMutation = useMutation({
    mutationFn: bulkDeleteSessions,
    onSuccess: (payload) => {
      const activeSessionId = selected?.id ?? selectedId;
      setDeletedSessionIds((current) => [
        ...new Set([...current, ...payload.deleted_ids]),
      ]);
      if (activeSessionId && payload.deleted_ids.includes(activeSessionId)) {
        resetActiveSessionState();
        onSelectedSessionChange?.(null);
      }
      setBulkSelectedIds([]);
      setBulkMode(false);
      setConfirmBulkDelete(false);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => {
      const message = `批量删除失败：${messageFromError(error)}`;
      setDeleteError(message);
      showActionNotice(message, "error");
    },
  });
  const visibleSessions = useMemo(() => {
    return sessions.filter(
      (session) =>
        !deletedSessionIds.includes(session.id) &&
        session.title.toLowerCase().includes(query.toLowerCase()),
    );
  }, [deletedSessionIds, query, sessions]);
  const selected =
    visibleSessions.find((item) => item.id === selectedId) ??
    (rememberedSelectedSession?.id === selectedId
      ? rememberedSelectedSession
      : null) ??
    visibleSessions[0] ??
    null;
  const selectedSessionId = selected?.id ?? "";
  const isSelectedSessionStreaming =
    isStreaming && activeStreamingSessionId === selectedSessionId;
  const { copiedSessionId, copySessionId, showActionNotice } =
    useSessionNotices({
      selected,
      selectedSessionId,
    });
  const {
    data: sessionTurns = EMPTY_SESSION_TURNS,
    dataUpdatedAt: sessionTurnsUpdatedAt,
    isSuccess: hasLoadedSessionTurns,
  } = useQuery({
    queryKey: sessionTurnsQueryKey(selectedSessionId),
    queryFn: ({ signal }) => listSessionTurns(selectedSessionId, signal),
    enabled: Boolean(selectedSessionId),
    staleTime: 15_000,
  });
  const {
    data: sessionTraces = EMPTY_SESSION_TRACES,
    dataUpdatedAt: sessionTracesUpdatedAt,
    isSuccess: hasLoadedSessionTraces,
  } = useQuery({
    queryKey: sessionTracesQueryKey(selectedSessionId),
    queryFn: ({ signal }) => listSessionTraces(selectedSessionId, signal),
    enabled: Boolean(selectedSessionId),
    staleTime: 15_000,
  });
  useSessionHistoryRestore({
    appliedHistoryKeyRef,
    hasLoadedSessionTurns,
    hasLoadedSessionTraces,
    insights,
    isStreaming: isSelectedSessionStreaming,
    messages,
    messagesSessionIdRef,
    selectedSessionId,
    sessionTraces,
    sessionTracesUpdatedAt,
    sessionTurns,
    sessionTurnsUpdatedAt,
    setDetectedFeatureIds,
    setInsights,
    setMessages,
    setRuntimeState,
    setStages,
    stages,
  });
  const hasCompletedQuestionAnswer = useMemo(() => {
    let hasUserQuestion = false;
    for (const message of messages) {
      if (message.role === "user" && message.content.trim()) {
        hasUserQuestion = true;
      }
      if (
        message.role === "assistant" &&
        message.status === "done" &&
        message.content.trim() &&
        hasUserQuestion
      ) {
        return true;
      }
    }
    return false;
  }, [messages]);
  const { feedbackByTurnId, feedbackPendingTurnId, submitFeedback } =
    useSessionFeedback({ showActionNotice });

  const {
    generatedReport,
    isReportPending,
    openReportDialog,
    preparedReport,
    reportDialog,
    reportError,
    reportFeatureId,
    reportTitle,
    setReportDialog,
    setReportFeatureId,
    setReportTitle,
    submitReport,
  } = useSessionReport({
    hasCompletedQuestionAnswer,
    isStreaming: isSelectedSessionStreaming,
    selected,
    showActionNotice,
  });
  const {
    attachments,
    clearUploadStatus,
    deleteAttachment,
    describeAttachment,
    fileInputRef,
    isFetchingAttachments,
    renameAttachment,
    uploadLog,
    uploadStatus,
  } = useSessionAttachments({
    onSessionCreated: setSelectedId,
    rememberSession,
    selected,
    selectedSessionId,
    showActionNotice,
  });
  const { cancelMessage, restoreActiveStreamSnapshot, sendMessage } =
    useSessionMessageStream({
    draft,
    insights,
    isStreaming,
    messagesSessionIdRef,
    messages,
    queryClient,
    rememberSession,
    runtimeState,
    selected,
    setActiveStreamingSessionId,
    setDetectedFeatureIds,
    setDraft,
    setInsights,
    setIsStreaming,
    setMessages,
    setSelectedId,
    setRuntimeState,
    setStages,
    showActionNotice,
  });
  useEffect(() => {
    if (
      selectedSessionId &&
      activeStreamingSessionId === selectedSessionId
    ) {
      restoreActiveStreamSnapshot(selectedSessionId);
    }
  }, [activeStreamingSessionId, restoreActiveStreamSnapshot, selectedSessionId]);
  const wikiPromotion = useSessionWikiPromotion({
    detectedFeatureIds,
    features,
    onOpenWiki,
    showActionNotice,
  });

  function rememberSession(session: SessionResponse) {
    setRememberedSelectedSession(session);
    upsertSession(queryClient, session, subjectQueryKey);
  }

  async function openAttachmentPicker() {
    try {
      const settings = await queryClient.fetchQuery({
        queryKey: ["system-settings"],
        queryFn: getSystemSettings,
        staleTime: 30_000,
      });
      if (!settings.session_attachments_enabled) {
        showActionNotice("该功能已被禁用", "error");
        return;
      }
      clearUploadStatus();
      fileInputRef.current?.click();
    } catch (error) {
      showActionNotice(
        `读取附件上传配置失败：${messageFromError(error)}`,
        "error",
      );
    }
  }

  return (
    <section
      className="workspace session-workspace"
      data-list-collapsed={listCollapsed}
      aria-label="会话工作台"
    >
      <SessionListPanel
        bulkMode={bulkMode}
        bulkSelectedIds={bulkSelectedIds}
        createPending={createMutation.isPending}
        deleteError={deleteCandidate ? "" : deleteError}
        isLoading={isLoading}
        listCollapsed={listCollapsed}
        menuSessionId={menuSessionId}
        onCancelBulkMode={() => {
          setBulkMode(false);
          setBulkSelectedIds([]);
        }}
        onConfirmBulkDelete={() => setConfirmBulkDelete(true)}
        onCreateSession={() => createMutation.mutate()}
        onDelete={(session) => {
          setDeleteError("");
          setDeleteCandidate(session);
          setMenuSessionId(null);
        }}
        onMenuToggle={(sessionId) =>
          setMenuSessionId((current) =>
            current === sessionId ? null : sessionId,
          )
        }
        onQueryChange={setQuery}
        onRename={(session) => {
          const next = window.prompt("编辑会话名称", session.title);
          if (next?.trim()) {
            updateMutation.mutate({
              sessionId: session.id,
              payload: { title: next.trim() },
            });
          }
        }}
        onSelect={selectSession}
        onShare={() => showActionNotice("暂不支持", "error")}
        onToggleBulkMode={(sessionId) => {
          setBulkMode(true);
          setBulkSelectedIds([sessionId]);
          setMenuSessionId(null);
        }}
        onToggleCollapsed={() => setListCollapsed((value) => !value)}
        onTogglePin={(session) =>
          updateMutation.mutate({
            sessionId: session.id,
            payload: { pinned: !session.pinned },
          })
        }
        onToggleSelect={(sessionId) =>
          setBulkSelectedIds((current) =>
            current.includes(sessionId)
              ? current.filter((id) => id !== sessionId)
              : [...current, sessionId],
          )
        }
        pendingDelete={deleteMutation.isPending}
        query={query}
        selectedSessionId={selected?.id ?? null}
        visibleSessions={visibleSessions}
      />

      <SessionConversationPanel
        copiedSessionId={copiedSessionId}
        createPending={createMutation.isPending}
        draft={draft}
        feedbackByTurnId={feedbackByTurnId}
        feedbackPendingTurnId={feedbackPendingTurnId}
        fileInputRef={fileInputRef}
        isStreaming={isSelectedSessionStreaming}
        messages={messages}
        onCopySessionId={() => void copySessionId()}
        onDraftChange={setDraft}
        onFeedback={submitFeedback}
        onOpenReportDialog={openReportDialog}
        onCancelMessage={cancelMessage}
        onSendMessage={() => void sendMessage()}
        onUploadClick={() => void openAttachmentPicker()}
        onUnsupportedAction={(message) => showActionNotice(message, "error")}
        onUploadFile={(file) => void uploadLog(file)}
        reportPending={isReportPending}
        selected={selected}
        selectedSessionId={selectedSessionId}
        uploadStatus={uploadStatus}
      />

      <InvestigationPanel
        attachments={attachments}
        insights={insights}
        isLoadingAttachments={
          Boolean(selectedSessionId) &&
          isFetchingAttachments &&
          attachments.length === 0
        }
        isStreaming={isSelectedSessionStreaming}
        onDescribeAttachment={describeAttachment}
        onDeleteAttachment={deleteAttachment}
        onPromoteAttachment={wikiPromotion.openDialog}
        onRenameAttachment={renameAttachment}
        runtimeState={runtimeState}
      />
      <SessionWorkspaceDialogs
        bulkSelectedCount={bulkSelectedIds.length}
        confirmBulkDelete={confirmBulkDelete}
        deleteCandidate={deleteCandidate}
        deleteError={deleteError}
        features={features}
        generatedReport={generatedReport}
        isBulkDeleting={bulkDeleteMutation.isPending}
        isDeleting={deleteMutation.isPending}
        isGeneratingReport={isReportPending}
        isPromotingAttachment={wikiPromotion.promoteMutation.isPending}
        onBulkDeleteCancel={() => {
          if (!bulkDeleteMutation.isPending) {
            setConfirmBulkDelete(false);
          }
        }}
        onBulkDeleteConfirm={() => bulkDeleteMutation.mutate(bulkSelectedIds)}
        onDeleteCancel={() => {
          if (!deleteMutation.isPending) {
            setDeleteCandidate(null);
          }
        }}
        onDeleteConfirm={() => {
          if (deleteCandidate) {
            deleteMutation.mutate(deleteCandidate.id);
          }
        }}
        onPromotionCancel={wikiPromotion.closeDialog}
        onPromotionConfirm={() => void wikiPromotion.promoteMutation.mutateAsync()}
        onPromotionDocumentNameChange={wikiPromotion.setDocumentName}
        onPromotionFeatureChange={wikiPromotion.setFeatureId}
        onPromotionOpenWiki={wikiPromotion.openPromotedWiki}
        onPromotionParentChange={wikiPromotion.setParentId}
        onOpenGeneratedReport={() => {
          setReportDialog(null);
          if (generatedReport?.feature_id) {
            onOpenReport?.({
              featureId: generatedReport.feature_id,
              reportId: generatedReport.id,
            });
          }
        }}
        onReportCancel={() => {
          if (!isReportPending) {
            setReportDialog(null);
          }
        }}
        onReportClose={() => setReportDialog(null)}
        onReportConfirm={submitReport}
        onReportFeatureChange={setReportFeatureId}
        onReportTitleChange={setReportTitle}
        reportDialog={reportDialog}
        reportError={reportError}
        reportExistingReportId={preparedReport?.existing_report_id ?? null}
        reportFeatureId={reportFeatureId}
        reportTitle={reportTitle}
        promotionAttachment={wikiPromotion.attachment}
        promotionCanSubmit={wikiPromotion.canSubmit}
        promotionDocumentName={wikiPromotion.documentName}
        promotionError={wikiPromotion.errorMessage}
        promotionFeatureId={wikiPromotion.featureId}
        promotionFolderOptions={wikiPromotion.folderOptions}
        promotionParentId={wikiPromotion.parentId}
        promotionResult={wikiPromotion.result}
        promotionTargetKind={wikiPromotion.targetKind}
        promotionTreeLoading={wikiPromotion.treeLoading}
      />
    </section>
  );
}
