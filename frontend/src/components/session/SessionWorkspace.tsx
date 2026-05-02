import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileText,
  FileUp,
  ListChecks,
  MoreHorizontal,
  Pencil,
  Pin,
  Plus,
  Search,
  SendHorizontal,
  Share2,
  Trash2,
} from "lucide-react";

import {
  bulkDeleteSessions,
  createSession,
  deleteSession,
  deleteSessionAttachment,
  generateSessionReport,
  listSessionAttachments,
  listFeatures,
  listSessions,
  listSessionTraces,
  listSessionTurns,
  postFeedback,
  postFrontendEvent,
  renameSessionAttachment,
  updateSession,
  updateSessionAttachment,
  uploadSessionAttachment,
} from "../../lib/api";
import { streamSessionMessage } from "../../lib/sse";
import type {
  AttachmentResponse,
  FeatureRead,
  FeedbackVerdict,
  ReportRead,
  SessionResponse,
  SessionTurnResponse,
  AgentTraceResponse,
} from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { InvestigationPanel } from "./InvestigationPanel";
import { MessageStream } from "./MessageStream";
import {
  askUserMessageFromEvent,
  createInitialStages,
  messageFromError,
  reduceStages,
  runtimeInsightFromEvent,
  textDeltaFromEvent,
  type ConversationMessage,
  type RuntimeInsight,
} from "./session-model";

interface ReportTarget {
  featureId: number;
  reportId: number;
}

interface SessionWorkspaceProps {
  onOpenReport?: (target: ReportTarget) => void;
}

const EMPTY_SESSION_TURNS: SessionTurnResponse[] = [];
const EMPTY_SESSION_TRACES: AgentTraceResponse[] = [];

export function SessionWorkspace({ onOpenReport }: SessionWorkspaceProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const copyToastTimeoutRef = useRef<number | null>(null);
  const actionNoticeTimeoutRef = useRef<number | null>(null);
  const appliedHistoryKeyRef = useRef<string | null>(null);
  const messagesSessionIdRef = useRef<string | null>(null);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [forceCodeInvestigation, setForceCodeInvestigation] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [insights, setInsights] = useState<RuntimeInsight[]>([]);
  const [stages, setStages] = useState(createInitialStages);
  const [uploadStatus, setUploadStatus] = useState("");
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
  const [actionNotice, setActionNotice] = useState("");
  const [detectedFeatureIds, setDetectedFeatureIds] = useState<number[]>([]);
  const [reportDialog, setReportDialog] = useState<
    "not-ready" | "confirm" | "success" | null
  >(null);
  const [reportFeatureId, setReportFeatureId] = useState("");
  const [reportTitle, setReportTitle] = useState("");
  const [reportError, setReportError] = useState("");
  const [generatedReport, setGeneratedReport] = useState<ReportRead | null>(
    null,
  );
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const [feedbackByTurnId, setFeedbackByTurnId] = useState<
    Record<string, FeedbackVerdict>
  >({});
  const [feedbackPendingTurnId, setFeedbackPendingTurnId] = useState<
    string | null
  >(null);
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
  const reportMutation = useMutation({
    mutationFn: ({
      session,
      featureId,
      title,
    }: {
      session: SessionResponse;
      featureId: number;
      title: string;
    }) =>
      generateSessionReport(session.id, {
        feature_id: featureId,
        title,
      }),
    onSuccess: (report) => {
      setGeneratedReport(report);
      setReportError("");
      setReportDialog("success");
      if (report.feature_id) {
        void queryClient.invalidateQueries({
          queryKey: ["reports", report.feature_id],
        });
      }
    },
    onError: (error) => {
      setReportError(`生成报告失败：${messageFromError(error)}`);
    },
  });
  const feedbackMutation = useMutation({
    mutationFn: async ({
      sessionId,
      turnId,
      verdict,
    }: {
      sessionId: string;
      turnId: string;
      verdict: FeedbackVerdict;
    }) => {
      await postFeedback({
        session_turn_id: turnId,
        feedback: verdict,
      });
      await postFrontendEvent({
        event_type: "feedback_submitted",
        session_id: sessionId,
        payload: {
          turn_id: turnId,
          feedback: verdict,
        },
      });
      return { turnId, verdict };
    },
    onMutate: ({ turnId }) => {
      setFeedbackPendingTurnId(turnId);
    },
    onSuccess: ({ turnId, verdict }) => {
      setFeedbackByTurnId((current) => ({ ...current, [turnId]: verdict }));
      setFeedbackPendingTurnId(null);
      showActionNotice(`已记录反馈：${feedbackLabel(verdict)}`);
    },
    onError: (error) => {
      setFeedbackPendingTurnId(null);
      showActionNotice(`提交反馈失败：${messageFromError(error)}`);
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
  useEffect(() => {
    setCopiedSessionId(null);
    setActionNotice("");
    if (copyToastTimeoutRef.current) {
      window.clearTimeout(copyToastTimeoutRef.current);
      copyToastTimeoutRef.current = null;
    }
    clearActionNoticeTimer();
  }, [selectedSessionId]);
  useEffect(() => {
    if (!selectedSessionId) {
      if (!isStreaming) {
        setMessages((current) => (current.length === 0 ? current : []));
      }
      appliedHistoryKeyRef.current = null;
      messagesSessionIdRef.current = null;
      return;
    }
    if (!hasLoadedSessionTurns || !hasLoadedSessionTraces || isStreaming) {
      return;
    }
    const historyKey = `${selectedSessionId}:${sessionTurnsUpdatedAt}:${sessionTracesUpdatedAt}`;
    if (appliedHistoryKeyRef.current === historyKey) {
      return;
    }
    const hasMoreLocalMessages =
      messagesSessionIdRef.current === selectedSessionId &&
      messages.length > sessionTurns.length;
    if (
      hasMoreLocalMessages &&
      insights.length > 0 &&
      stages.some((stage) => stage.status !== "pending")
    ) {
      appliedHistoryKeyRef.current = historyKey;
      return;
    }
    if (!hasMoreLocalMessages) {
      setMessages(messagesFromSessionTurns(sessionTurns));
    }
    setInsights(insightsFromSessionHistory(sessionTurns, sessionTraces));
    setStages(stagesFromSessionTraces(sessionTraces));
    messagesSessionIdRef.current = selectedSessionId;
    appliedHistoryKeyRef.current = historyKey;
  }, [
    hasLoadedSessionTurns,
    hasLoadedSessionTraces,
    insights.length,
    isStreaming,
    messages.length,
    selectedSessionId,
    sessionTraces,
    sessionTracesUpdatedAt,
    sessionTurns,
    sessionTurnsUpdatedAt,
    stages,
  ]);
  useEffect(() => {
    return () => {
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
      clearActionNoticeTimer();
    };
  }, []);
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

  function openReportDialog() {
    if (!selected) {
      showActionNotice("请先创建会话后再生成报告");
      return;
    }
    if (!hasCompletedQuestionAnswer || isStreaming) {
      setReportDialog("not-ready");
      setReportError("");
      return;
    }
    const inferredFeatureId = detectedFeatureIds.find((id) =>
      features.some((feature) => feature.id === id),
    );
    const defaultFeatureId = inferredFeatureId ?? features[0]?.id;
    setReportFeatureId(defaultFeatureId ? String(defaultFeatureId) : "");
    setReportTitle(`${selected.title}定位报告`);
    setReportError("");
    setGeneratedReport(null);
    setReportDialog("confirm");
  }

  function submitReport() {
    if (!selected || !reportFeatureId) {
      return;
    }
    reportMutation.mutate({
      session: selected,
      featureId: Number(reportFeatureId),
      title: reportTitle.trim() || `${selected.title}定位报告`,
    });
  }

  function rememberSession(session: SessionResponse) {
    setLocalSessions((current) => [
      session,
      ...current.filter((item) => item.id !== session.id),
    ]);
    upsertSession(queryClient, session);
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content || isStreaming) {
      return;
    }

    let target = selected;
    if (!target) {
      try {
        target = await createSession(content.slice(0, 28) || "新的研发会话");
        setSelectedId(target.id);
        rememberSession(target);
      } catch (error) {
        showActionNotice(`创建默认会话失败：${messageFromError(error)}`);
        return;
      }
    }

    const userMessageId = `msg_user_${Date.now()}`;
    const assistantMessageId = `msg_assistant_${Date.now()}`;
    setDraft("");
    setStages(createInitialStages());
    setInsights([]);
    setDetectedFeatureIds([]);
    setIsStreaming(true);
    messagesSessionIdRef.current = target.id;
    setMessages((current) => [
      ...current,
      { id: userMessageId, role: "user", content },
      {
        id: assistantMessageId,
        role: "assistant",
        content: "",
        status: "streaming",
      },
    ]);

    try {
      await streamSessionMessage({
        sessionId: target.id,
        content,
        force_code_investigation: forceCodeInvestigation,
        onEvent: (event) => {
          setStages((current) => reduceStages(current, event));
          const insight = runtimeInsightFromEvent(event);
          if (insight) {
            setInsights((current) => [...current, insight]);
          }
          if (event.type === "scope_detection") {
            const ids = featureIdsFromEvent(event.data);
            if (ids.length > 0) {
              setDetectedFeatureIds((current) => [
                ...new Set([...ids, ...current]),
              ]);
            }
          }
          const delta = textDeltaFromEvent(event);
          if (delta) {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? { ...message, content: `${message.content}${delta}` }
                  : message,
              ),
            );
          }
          const askUserMessage = askUserMessageFromEvent(event);
          if (askUserMessage) {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: message.content
                        ? `${message.content}\n\n${askUserMessage}`
                        : askUserMessage,
                      status: "done",
                    }
                  : message,
              ),
            );
          }
          if (event.type === "error") {
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: String(event.data.message ?? "Agent 运行失败"),
                      status: "error",
                    }
                  : message,
              ),
            );
          }
          if (event.type === "done") {
            const turnId =
              typeof event.data.turn_id === "string"
                ? event.data.turn_id
                : null;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      status: "done",
                      turnId: turnId ?? message.turnId,
                    }
                  : message,
              ),
            );
          }
        },
      });
      void queryClient.invalidateQueries({
        queryKey: sessionTurnsQueryKey(target.id),
      });
      void queryClient.invalidateQueries({
        queryKey: sessionTracesQueryKey(target.id),
      });
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: messageFromError(error), status: "error" }
            : message,
        ),
      );
      setStages((current) =>
        current.map((stage) =>
          stage.status === "active" ? { ...stage, status: "error" } : stage,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  }

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
        setSelectedId(target.id);
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

  function clearActionNoticeTimer() {
    if (actionNoticeTimeoutRef.current) {
      window.clearTimeout(actionNoticeTimeoutRef.current);
      actionNoticeTimeoutRef.current = null;
    }
  }

  function showActionNotice(message: string) {
    clearActionNoticeTimer();
    setActionNotice(message);
    actionNoticeTimeoutRef.current = window.setTimeout(() => {
      setActionNotice("");
      actionNoticeTimeoutRef.current = null;
    }, 2800);
  }

  async function copySessionId() {
    if (!selected) {
      return;
    }
    try {
      await copyTextToClipboard(selected.id);
      setCopiedSessionId(selected.id);
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
      copyToastTimeoutRef.current = window.setTimeout(() => {
        setCopiedSessionId(null);
        copyToastTimeoutRef.current = null;
      }, 1000);
    } catch {
      setCopiedSessionId(null);
    }
  }

  return (
    <section
      className="workspace session-workspace"
      data-list-collapsed={listCollapsed}
      aria-label="会话工作台"
    >
      <aside
        className="list-panel"
        data-collapsed={listCollapsed}
        role="region"
        aria-label="会话列表"
      >
        <button
          aria-label={listCollapsed ? "展开会话列表" : "收起会话列表"}
          className="edge-collapse-button secondary"
          data-collapsed={listCollapsed}
          onClick={() => setListCollapsed((value) => !value)}
          title={listCollapsed ? "展开会话列表" : "收起会话列表"}
          type="button"
        >
          {listCollapsed ? (
            <ChevronRight aria-hidden="true" size={15} />
          ) : (
            <ChevronLeft aria-hidden="true" size={15} />
          )}
        </button>
        {listCollapsed ? (
          <div className="collapsed-panel-label">会话</div>
        ) : (
          <>
            <div className="list-toolbar">
              <label className="search-field">
                <Search aria-hidden="true" size={16} />
                <Input
                  aria-label="搜索会话"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索会话"
                  value={query}
                />
              </label>
              <Button
                aria-label="新建会话"
                className="icon-only"
                disabled={createMutation.isPending}
                icon={<Plus size={17} />}
                onClick={() => createMutation.mutate()}
                title="新建会话"
                type="button"
              />
            </div>
            {bulkMode ? (
              <div className="bulk-toolbar">
                <span>已选择 {bulkSelectedIds.length} 个</span>
                <div className="row-actions">
                  <Button
                    disabled={bulkSelectedIds.length === 0}
                    onClick={() => setConfirmBulkDelete(true)}
                    type="button"
                    variant="danger"
                  >
                    批量删除
                  </Button>
                  <Button
                    onClick={() => {
                      setBulkMode(false);
                      setBulkSelectedIds([]);
                    }}
                    type="button"
                    variant="secondary"
                  >
                    取消
                  </Button>
                </div>
              </div>
            ) : null}
            {deleteError && !deleteCandidate ? (
              <div className="inline-alert danger" role="alert">
                {deleteError}
              </div>
            ) : null}

            <div className="list-scroll">
              {isLoading ? <p className="empty-note">正在加载会话</p> : null}
              {!isLoading && visibleSessions.length === 0 ? (
                <div className="empty-block">
                  <p>暂无会话</p>
                  <span>点击右上角加号创建一次新的研发问答。</span>
                </div>
              ) : null}
              {visibleSessions.map((session) => (
                <SessionListItem
                  active={selected?.id === session.id}
                  bulkMode={bulkMode}
                  checked={bulkSelectedIds.includes(session.id)}
                  key={session.id}
                  onClick={() => setSelectedId(session.id)}
                  onDelete={() => {
                    setDeleteError("");
                    setDeleteCandidate(session);
                    setMenuSessionId(null);
                  }}
                  onMenuToggle={() =>
                    setMenuSessionId((current) =>
                      current === session.id ? null : session.id,
                    )
                  }
                  onRename={() => {
                    const next = window.prompt("编辑会话名称", session.title);
                    if (next?.trim()) {
                      updateMutation.mutate({
                        sessionId: session.id,
                        payload: { title: next.trim() },
                      });
                    }
                  }}
                  onShare={() => showActionNotice("暂不支持")}
                  onToggleBulkMode={() => {
                    setBulkMode(true);
                    setBulkSelectedIds([session.id]);
                    setMenuSessionId(null);
                  }}
                  onTogglePin={() =>
                    updateMutation.mutate({
                      sessionId: session.id,
                      payload: { pinned: !session.pinned },
                    })
                  }
                  onToggleSelect={() =>
                    setBulkSelectedIds((current) =>
                      current.includes(session.id)
                        ? current.filter((id) => id !== session.id)
                        : [...current, session.id],
                    )
                  }
                  menuOpen={menuSessionId === session.id}
                  pendingDelete={deleteMutation.isPending}
                  session={session}
                />
              ))}
            </div>
          </>
        )}
      </aside>

      <section
        className="conversation-panel"
        role="region"
        aria-label="会话消息"
      >
        <div className="page-header compact">
          <div>
            <div className="session-title-row">
              <h1>{selected?.title ?? "新会话"}</h1>
              {selected ? (
                <button
                  aria-label={`复制完整会话 ID ${selected.id}`}
                  className="session-id-pill"
                  onClick={() => void copySessionId()}
                  title={`点击复制完整会话 ID：${selected.id}`}
                  type="button"
                >
                  <span>{formatSessionIdPreview(selected.id)}</span>
                  {copiedSessionId === selected.id ? (
                    <span className="session-copy-popover" role="status">
                      复制成功
                    </span>
                  ) : null}
                </button>
              ) : null}
            </div>
            <p>上传日志、绑定特性和仓库后，CodeAsk 会按阶段给出证据化回答。</p>
          </div>
          <div className="header-actions">
            <Badge>{selected?.status ?? "ready"}</Badge>
          </div>
        </div>
        {actionNotice ? (
          <div className="action-banner" role="status">
            {actionNotice}
          </div>
        ) : null}

        <MessageStream
          feedbackByTurnId={feedbackByTurnId}
          feedbackPendingTurnId={feedbackPendingTurnId}
          messages={messages}
          onCopyCode={(code) => copyTextToClipboard(code)}
          onCopyMessage={(message) => copyTextToClipboard(message.content)}
          onFeedback={(turnId, verdict) => {
            if (
              !selectedSessionId ||
              feedbackPendingTurnId === turnId ||
              feedbackByTurnId[turnId]
            ) {
              return;
            }
            feedbackMutation.mutate({
              sessionId: selectedSessionId,
              turnId,
              verdict,
            });
          }}
          onUnsupportedAction={showActionNotice}
        />

        <div className="composer" role="region" aria-label="会话输入操作区">
          <Textarea
            aria-label="会话输入"
            onChange={(event) => setDraft(event.target.value)}
            placeholder="描述你遇到的问题，或粘贴关键日志片段"
            value={draft}
          />
          <div className="composer-actions">
            <input
              accept=".log,.txt,.md"
              className="visually-hidden"
              onChange={(event) => void uploadLog(event.target.files?.[0])}
              ref={fileInputRef}
              type="file"
            />
            <Button
              disabled={createMutation.isPending}
              icon={<FileUp size={16} />}
              onClick={() => fileInputRef.current?.click()}
              type="button"
              variant="quiet"
            >
              上传日志
            </Button>
            {uploadStatus ? (
              <span className="upload-status">{uploadStatus}</span>
            ) : null}
            <label className="checkbox-row">
              <input
                checked={forceCodeInvestigation}
                onChange={(event) => {
                  const checked = event.target.checked;
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
                type="checkbox"
              />
              <span>强制代码调查</span>
            </label>
            <Button
              disabled={!selected || reportMutation.isPending}
              icon={<FileText size={16} />}
              onClick={openReportDialog}
              type="button"
              variant="secondary"
            >
              生成报告
            </Button>
            <Button
              disabled={!draft.trim() || isStreaming}
              icon={<SendHorizontal size={16} />}
              onClick={() => void sendMessage()}
              type="button"
              variant="primary"
            >
              {isStreaming ? "发送中" : "发送"}
            </Button>
          </div>
        </div>
      </section>

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
        onRenameAttachment={renameAttachment}
        stages={stages}
      />
      {deleteCandidate ? (
        <DeleteSessionDialog
          errorMessage={deleteError}
          isDeleting={deleteMutation.isPending}
          onCancel={() => {
            if (!deleteMutation.isPending) {
              setDeleteCandidate(null);
            }
          }}
          onConfirm={() => deleteMutation.mutate(deleteCandidate.id)}
          sessionTitle={deleteCandidate.title}
        />
      ) : null}
      {confirmBulkDelete ? (
        <DeleteSessionDialog
          errorMessage={deleteError}
          isDeleting={bulkDeleteMutation.isPending}
          onCancel={() => {
            if (!bulkDeleteMutation.isPending) {
              setConfirmBulkDelete(false);
            }
          }}
          onConfirm={() => bulkDeleteMutation.mutate(bulkSelectedIds)}
          sessionTitle={`${bulkSelectedIds.length} 个会话`}
        />
      ) : null}
      {reportDialog === "not-ready" ? (
        <ReportReadinessDialog onClose={() => setReportDialog(null)} />
      ) : null}
      {reportDialog === "confirm" ? (
        <ReportConfirmDialog
          errorMessage={reportError}
          featureId={reportFeatureId}
          features={features}
          isGenerating={reportMutation.isPending}
          onCancel={() => {
            if (!reportMutation.isPending) {
              setReportDialog(null);
            }
          }}
          onConfirm={submitReport}
          onFeatureChange={setReportFeatureId}
          onTitleChange={setReportTitle}
          title={reportTitle}
        />
      ) : null}
      {reportDialog === "success" && generatedReport ? (
        <ReportSuccessDialog
          onClose={() => setReportDialog(null)}
          onOpen={() => {
            setReportDialog(null);
            if (generatedReport.feature_id) {
              onOpenReport?.({
                featureId: generatedReport.feature_id,
                reportId: generatedReport.id,
              });
            }
          }}
          report={generatedReport}
        />
      ) : null}
    </section>
  );
}

function featureIdsFromEvent(data: Record<string, unknown>) {
  const value = data.feature_ids;
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (item): item is number =>
      typeof item === "number" && Number.isInteger(item),
  );
}

function formatSessionIdPreview(sessionId: string) {
  if (sessionId.startsWith("sess_")) {
    return `sess_${sessionId.slice(5, 9)}`;
  }
  return sessionId.length <= 9 ? sessionId : sessionId.slice(0, 9);
}

function feedbackLabel(verdict: FeedbackVerdict) {
  if (verdict === "solved") {
    return "已解决";
  }
  if (verdict === "partial") {
    return "部分解决";
  }
  return "没解决";
}

async function copyTextToClipboard(value: string) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall through to the textarea fallback for browser contexts that expose
      // clipboard but reject access without a permission prompt.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    throw new Error("copy failed");
  }
}

function sessionAttachmentsQueryKey(sessionId: string) {
  return ["session-attachments", sessionId] as const;
}

function sessionTurnsQueryKey(sessionId: string) {
  return ["session-turns", sessionId] as const;
}

function sessionTracesQueryKey(sessionId: string) {
  return ["session-traces", sessionId] as const;
}

function messagesFromSessionTurns(
  turns: SessionTurnResponse[],
): ConversationMessage[] {
  return turns.map((turn) => ({
    id: turn.id,
    role: turn.role === "agent" ? "assistant" : "user",
    content: turn.content,
    status: turn.role === "agent" ? "done" : undefined,
    turnId: turn.role === "agent" ? turn.id : undefined,
  }));
}

const STAGE_LABELS: Record<string, string> = {
  input_analysis: "输入分析",
  scope_detection: "范围判断",
  knowledge_retrieval: "知识检索",
  sufficiency_judgement: "充分性判断",
  code_investigation: "代码调查",
  evidence_synthesis: "证据合成",
  answer_finalization: "最终回答",
  report_drafting: "报告草稿",
  ask_user: "等待补充",
};

function stagesFromSessionTraces(traces: AgentTraceResponse[]) {
  const visibleTraces = traces.filter((trace) => !isHiddenStage(trace.stage));
  if (visibleTraces.length === 0) {
    return createInitialStages();
  }

  const stageRows = createInitialStages();
  const byKey = new Map(stageRows.map((stage) => [stage.key, stage]));
  for (const trace of visibleTraces) {
    if (!byKey.has(trace.stage)) {
      byKey.set(trace.stage, {
        key: trace.stage,
        label: STAGE_LABELS[trace.stage] ?? trace.stage,
        detail: "Agent 进入该阶段",
        status: "pending",
      });
    }
  }

  for (const trace of visibleTraces) {
    const stage = byKey.get(trace.stage);
    if (!stage) {
      continue;
    }
    if (trace.event_type === "stage_enter") {
      stage.status = stage.status === "done" ? "done" : "active";
      stage.detail = "Agent 已进入该阶段";
    }
    if (trace.event_type === "stage_exit") {
      stage.status = tracePayloadHasError(trace.payload) ? "error" : "done";
      stage.detail = stageExitDetail(trace.payload);
    }
  }

  return Array.from(byKey.values());
}

function insightsFromSessionHistory(
  turns: SessionTurnResponse[],
  traces: AgentTraceResponse[],
): RuntimeInsight[] {
  const insights: RuntimeInsight[] = [];
  for (const trace of traces) {
    const event = agentEventFromTrace(trace);
    if (!event) {
      continue;
    }
    const insight = runtimeInsightFromEvent(event);
    if (insight) {
      insights.push({ ...insight, id: trace.id });
    }
  }
  for (const turn of turns) {
    for (const insight of evidenceInsightsFromTurn(turn)) {
      insights.push(insight);
    }
  }
  return insights;
}

function agentEventFromTrace(trace: AgentTraceResponse) {
  const payload = recordValue(trace.payload);
  if (trace.event_type === "scope_decision") {
    return {
      type: "scope_detection" as const,
      data: recordValue(payload.output),
    };
  }
  if (trace.event_type === "sufficiency_decision") {
    return {
      type: "sufficiency_judgement" as const,
      data: recordValue(payload.output),
    };
  }
  if (trace.event_type === "tool_call") {
    return { type: "tool_call" as const, data: payload };
  }
  if (trace.event_type === "tool_result") {
    return { type: "tool_result" as const, data: payload };
  }
  if (trace.event_type !== "llm_event") {
    return null;
  }
  if (payload.type === "tool_call_done") {
    return { type: "tool_call" as const, data: recordValue(payload.data) };
  }
  if (payload.type === "error") {
    return { type: "error" as const, data: recordValue(payload.data) };
  }
  return null;
}

function evidenceInsightsFromTurn(turn: SessionTurnResponse): RuntimeInsight[] {
  const evidence = recordValue(turn.evidence);
  const items = Array.isArray(evidence.items) ? evidence.items : [];
  return items
    .map((item, index) => {
      const row = recordValue(item);
      const id = stringValue(row.id) ?? `${turn.id}_evidence_${index}`;
      const summary = stringValue(row.summary) ?? "已收集证据";
      const data = recordValue(row.data);
      const path = stringValue(data.path);
      const result = recordValue(data.result);
      const resultData = recordValue(result.data);
      const resultPath = stringValue(resultData.path);
      return {
        id,
        kind: "evidence",
        title: `证据：${summary}`,
        detail: [stringValue(row.type), path ?? resultPath]
          .filter(Boolean)
          .join(" · "),
      };
    })
    .filter((item) => item.detail || item.title);
}

function isHiddenStage(stage: string) {
  return stage === "initialize" || stage === "terminate";
}

function tracePayloadHasError(payload: unknown) {
  const result = recordValue(recordValue(payload).result);
  return typeof result.error === "string" && result.error.length > 0;
}

function stageExitDetail(payload: unknown) {
  const result = recordValue(recordValue(payload).result);
  const error = stringValue(result.error);
  if (error) {
    return `阶段失败：${error}`;
  }
  const next = stringValue(result.next);
  return next ? `已完成，下一步：${STAGE_LABELS[next] ?? next}` : "已完成";
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function upsertAttachment(
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

function upsertSession(queryClient: QueryClient, session: SessionResponse) {
  queryClient.setQueryData<SessionResponse[]>(["sessions"], (current = []) => {
    const next = current.filter((item) => item.id !== session.id);
    return [session, ...next];
  });
}

function ReportReadinessDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-readiness-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon warning">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-readiness-title">暂不能生成报告</h2>
          <p>至少完成一次问答，并得到可汇总的回答后，才能生成问题定位报告。</p>
          <div className="dialog-actions">
            <Button onClick={onClose} type="button" variant="primary">
              知道了
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function ReportConfirmDialog({
  errorMessage,
  featureId,
  features,
  isGenerating,
  onCancel,
  onConfirm,
  onFeatureChange,
  onTitleChange,
  title,
}: {
  errorMessage: string;
  featureId: string;
  features: FeatureRead[];
  isGenerating: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onFeatureChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  title: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-confirm-title"
        aria-modal="true"
        className="confirm-dialog report-dialog"
        role="dialog"
      >
        <div className="dialog-icon">
          <FileText aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-confirm-title">生成问题定位报告</h2>
          <p>报告会沉淀到绑定特性的“问题报告”中，生成后可以直接跳转查看。</p>
          <label className="field-label compact">
            绑定特性
            <select
              className="input"
              onChange={(event) => onFeatureChange(event.target.value)}
              value={featureId}
            >
              <option value="">请选择特性</option>
              {features.map((feature) => (
                <option key={feature.id} value={feature.id}>
                  {feature.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label compact">
            报告标题
            <Input
              onChange={(event) => onTitleChange(event.target.value)}
              value={title}
            />
          </label>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button
              disabled={isGenerating}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={!featureId || !title.trim() || isGenerating}
              onClick={onConfirm}
              type="button"
              variant="primary"
            >
              {isGenerating ? "生成中" : "确认生成"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function ReportSuccessDialog({
  onClose,
  onOpen,
  report,
}: {
  onClose: () => void;
  onOpen: () => void;
  report: ReportRead;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="report-success-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon success">
          <CheckCircle2 aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="report-success-title">报告已生成</h2>
          <p>“{report.title}”已经写入特性的问题报告列表。</p>
          <div className="dialog-actions">
            <Button onClick={onClose} type="button" variant="secondary">
              留在会话
            </Button>
            <Button onClick={onOpen} type="button" variant="primary">
              查看报告
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function DeleteSessionDialog({
  errorMessage,
  isDeleting,
  onCancel,
  onConfirm,
  sessionTitle,
}: {
  errorMessage: string;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  sessionTitle: string;
}) {
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="delete-session-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className="dialog-icon danger">
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="delete-session-title">删除会话</h2>
          <p>确认删除“{sessionTitle}”？删除后会话记录和关联附件将被移除。</p>
          {errorMessage ? (
            <div className="inline-alert danger in-dialog" role="alert">
              {errorMessage}
            </div>
          ) : null}
          <div className="dialog-actions">
            <Button
              disabled={isDeleting}
              onClick={onCancel}
              type="button"
              variant="secondary"
            >
              取消
            </Button>
            <Button
              disabled={isDeleting}
              onClick={onConfirm}
              type="button"
              variant="danger"
            >
              {isDeleting ? "删除中" : "确认删除"}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function SessionListItem({
  active,
  bulkMode,
  checked,
  menuOpen,
  onClick,
  onDelete,
  onMenuToggle,
  onRename,
  onShare,
  onToggleBulkMode,
  onTogglePin,
  onToggleSelect,
  pendingDelete,
  session,
}: {
  active: boolean;
  bulkMode: boolean;
  checked: boolean;
  menuOpen: boolean;
  onClick: () => void;
  onDelete: () => void;
  onMenuToggle: () => void;
  onRename: () => void;
  onShare: () => void;
  onToggleBulkMode: () => void;
  onTogglePin: () => void;
  onToggleSelect: () => void;
  pendingDelete: boolean;
  session: SessionResponse;
}) {
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const [menuPosition, setMenuPosition] = useState({ left: 0, top: 0 });

  useLayoutEffect(() => {
    if (!menuOpen || !menuButtonRef.current) {
      return;
    }

    function updatePosition() {
      const rect = menuButtonRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }
      setMenuPosition({
        left: Math.max(8, rect.right - 166),
        top: rect.bottom + 6,
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [menuOpen]);

  const menu = menuOpen ? (
    <div
      className="row-menu"
      role="menu"
      style={{ left: menuPosition.left, top: menuPosition.top }}
    >
      <button onClick={onRename} role="menuitem" type="button">
        <Pencil aria-hidden="true" size={15} />
        编辑名称
      </button>
      <button onClick={onShare} role="menuitem" type="button">
        <Share2 aria-hidden="true" size={15} />
        分享
      </button>
      <button onClick={onTogglePin} role="menuitem" type="button">
        <Pin aria-hidden="true" size={15} />
        {session.pinned ? "取消置顶" : "置顶"}
      </button>
      <button onClick={onToggleBulkMode} role="menuitem" type="button">
        <ListChecks aria-hidden="true" size={15} />
        批量操作
      </button>
      <button
        className="danger"
        onClick={onDelete}
        role="menuitem"
        type="button"
      >
        <Trash2 aria-hidden="true" size={15} />
        删除
      </button>
    </div>
  ) : null;

  return (
    <div className="list-row" data-active={active}>
      {bulkMode ? (
        <label className="row-checkbox">
          <input checked={checked} onChange={onToggleSelect} type="checkbox" />
        </label>
      ) : null}
      <button
        aria-label={session.title}
        className="list-item"
        data-active={active}
        onClick={onClick}
        type="button"
      >
        <span className="item-title">
          {session.pinned ? <Pin aria-hidden="true" size={13} /> : null}
          {session.title}
        </span>
        <span className="item-meta">
          {new Date(session.updated_at).toLocaleString()}
        </span>
      </button>
      <button
        aria-label={`打开会话 ${session.title} 的更多操作`}
        className="list-menu-button"
        disabled={pendingDelete}
        onClick={onMenuToggle}
        ref={menuButtonRef}
        title="更多操作"
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={16} />
      </button>
      {menu ? createPortal(menu, document.body) : null}
    </div>
  );
}
