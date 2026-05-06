import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bulkDeleteSessions,
  createSession,
  deleteSession,
  listFeatures,
  listSessions,
  listSessionTraces,
  listSessionTurns,
  postFrontendEvent,
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
  sessionTurnsQueryKey,
  upsertSession,
} from "./session-cache";
import {
  createInitialStages,
  messageFromError,
  type ConversationMessage,
  type RuntimeInsight,
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
  onOpenReport?: (target: ReportTarget) => void;
  onOpenWiki?: (target: { featureId: number; nodeId: number }) => void;
}

const EMPTY_SESSION_TURNS: SessionTurnResponse[] = [];
const EMPTY_SESSION_TRACES: AgentTraceResponse[] = [];

export function SessionWorkspace({ onOpenReport, onOpenWiki }: SessionWorkspaceProps) {
  const queryClient = useQueryClient();
  const appliedHistoryKeyRef = useRef<string | null>(null);
  const messagesSessionIdRef = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [forceCodeInvestigation, setForceCodeInvestigation] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [insights, setInsights] = useState<RuntimeInsight[]>([]);
  const [stages, setStages] = useState(createInitialStages);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [localSessions, setLocalSessions] = useState<SessionResponse[]>([]);
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
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: listSessions,
  });
  const { data: features = [] } = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const createMutation = useMutation({
    mutationFn: () => createSession("新的研发会话"),
    onSuccess: (session) => {
      setSelectedId(session.id);
      rememberSession(session);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: (_unused, sessionId) => {
      setDeletedSessionIds((current) => [...new Set([...current, sessionId])]);
      setLocalSessions((current) =>
        current.filter((session) => session.id !== sessionId),
      );
      setDeleteCandidate(null);
      setDeleteError("");
      if (selectedId === sessionId) {
        setSelectedId(null);
        setMessages([]);
        messagesSessionIdRef.current = null;
        setInsights([]);
        setStages(createInitialStages());
      }
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => {
      setDeleteError(`删除会话失败：${messageFromError(error)}`);
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
      setDeletedSessionIds((current) => [
        ...new Set([...current, ...payload.deleted_ids]),
      ]);
      setLocalSessions((current) =>
        current.filter((session) => !payload.deleted_ids.includes(session.id)),
      );
      if (selectedId && payload.deleted_ids.includes(selectedId)) {
        setSelectedId(null);
        setMessages([]);
        messagesSessionIdRef.current = null;
        setInsights([]);
        setStages(createInitialStages());
      }
      setBulkSelectedIds([]);
      setBulkMode(false);
      setConfirmBulkDelete(false);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => {
      setDeleteError(`批量删除失败：${messageFromError(error)}`);
    },
  });
  const sessionRows = useMemo(() => {
    const rows = new Map<string, SessionResponse>();
    for (const session of localSessions) {
      rows.set(session.id, session);
    }
    for (const session of sessions) {
      rows.set(session.id, session);
    }
    return Array.from(rows.values());
  }, [localSessions, sessions]);
  const visibleSessions = useMemo(() => {
    return sessionRows.filter(
      (session) =>
        !deletedSessionIds.includes(session.id) &&
        session.title.toLowerCase().includes(query.toLowerCase()),
    );
  }, [deletedSessionIds, query, sessionRows]);
  const selected =
    visibleSessions.find((item) => item.id === selectedId) ??
    visibleSessions[0] ??
    null;
  const selectedSessionId = selected?.id ?? "";
  const { actionNotice, copiedSessionId, copySessionId, showActionNotice } =
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
    isStreaming,
    messages,
    messagesSessionIdRef,
    selectedSessionId,
    sessionTraces,
    sessionTracesUpdatedAt,
    sessionTurns,
    sessionTurnsUpdatedAt,
    setInsights,
    setMessages,
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
    openReportDialog,
    reportDialog,
    reportError,
    reportFeatureId,
    reportMutation,
    reportTitle,
    setReportDialog,
    setReportFeatureId,
    setReportTitle,
    submitReport,
  } = useSessionReport({
    detectedFeatureIds,
    features,
    hasCompletedQuestionAnswer,
    isStreaming,
    selected,
    showActionNotice,
  });
  const {
    attachments,
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
  const { sendMessage } = useSessionMessageStream({
    draft,
    forceCodeInvestigation,
    isStreaming,
    messagesSessionIdRef,
    queryClient,
    rememberSession,
    selected,
    setDetectedFeatureIds,
    setDraft,
    setInsights,
    setIsStreaming,
    setMessages,
    setSelectedId,
    setStages,
    showActionNotice,
  });
  const wikiPromotion = useSessionWikiPromotion({
    detectedFeatureIds,
    features,
    onOpenWiki,
    showActionNotice,
  });

  function rememberSession(session: SessionResponse) {
    setLocalSessions((current) => [
      session,
      ...current.filter((item) => item.id !== session.id),
    ]);
    upsertSession(queryClient, session);
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
        onSelect={setSelectedId}
        onShare={() => showActionNotice("暂不支持")}
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
        actionNotice={actionNotice}
        copiedSessionId={copiedSessionId}
        createPending={createMutation.isPending}
        draft={draft}
        feedbackByTurnId={feedbackByTurnId}
        feedbackPendingTurnId={feedbackPendingTurnId}
        fileInputRef={fileInputRef}
        forceCodeInvestigation={forceCodeInvestigation}
        isStreaming={isStreaming}
        messages={messages}
        onCopySessionId={() => void copySessionId()}
        onDraftChange={setDraft}
        onFeedback={submitFeedback}
        onForceCodeInvestigationChange={(checked) => {
          setForceCodeInvestigation(checked);
          if (checked && selectedSessionId) {
            void postFrontendEvent({
              event_type: "force_deeper_investigation",
              session_id: selectedSessionId,
              payload: {
                turn_count: messages.length,
                streaming: isStreaming,
              },
            }).catch(() => undefined);
          }
        }}
        onOpenReportDialog={openReportDialog}
        onSendMessage={() => void sendMessage()}
        onUnsupportedAction={showActionNotice}
        onUploadFile={(file) => void uploadLog(file)}
        reportPending={reportMutation.isPending}
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
        isStreaming={isStreaming}
        onDescribeAttachment={describeAttachment}
        onDeleteAttachment={deleteAttachment}
        onPromoteAttachment={wikiPromotion.openDialog}
        onRenameAttachment={renameAttachment}
        stages={stages}
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
        isGeneratingReport={reportMutation.isPending}
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
          if (!reportMutation.isPending) {
            setReportDialog(null);
          }
        }}
        onReportClose={() => setReportDialog(null)}
        onReportConfirm={submitReport}
        onReportFeatureChange={setReportFeatureId}
        onReportTitleChange={setReportTitle}
        reportDialog={reportDialog}
        reportError={reportError}
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
