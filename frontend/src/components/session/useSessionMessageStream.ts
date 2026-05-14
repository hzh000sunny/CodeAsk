import { useRef, type Dispatch, type RefObject, type SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";

import {
  abortSessionTurn,
  createSession,
  generateSessionTitle,
} from "../../lib/api";
import { streamSessionMessage } from "../../lib/sse";
import type { SessionResponse } from "../../types/api";
import {
  sessionTracesQueryKey,
  sessionTurnsQueryKey,
} from "./session-cache";
import { featureIdsFromEvent } from "./session-history";
import {
  appendRuntimeInsight,
  askUserMessageFromEvent,
  createInitialStages,
  messageFromError,
  reduceStages,
  removeOpencodeRunningInsight,
  runtimeInsightFromEvent,
  runtimeStateFromEvent,
  textDeltaFromEvent,
  type ConversationMessage,
  type RuntimeInsight,
  type RuntimeSessionState,
  type RuntimeStage,
} from "./session-model";
import { createReasoningLeakGuard } from "./reasoning-leak-guard";

export function useSessionMessageStream({
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
}: {
  draft: string;
  insights: RuntimeInsight[];
  isStreaming: boolean;
  messages: ConversationMessage[];
  messagesSessionIdRef: RefObject<string | null>;
  queryClient: QueryClient;
  rememberSession: (session: SessionResponse) => void;
  runtimeState: RuntimeSessionState | null;
  selected: SessionResponse | null;
  setActiveStreamingSessionId: Dispatch<SetStateAction<string | null>>;
  setDetectedFeatureIds: Dispatch<SetStateAction<number[]>>;
  setDraft: Dispatch<SetStateAction<string>>;
  setInsights: Dispatch<SetStateAction<RuntimeInsight[]>>;
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setMessages: Dispatch<SetStateAction<ConversationMessage[]>>;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  setRuntimeState: Dispatch<SetStateAction<RuntimeSessionState | null>>;
  setStages: Dispatch<SetStateAction<RuntimeStage[]>>;
  showActionNotice: (message: string, tone?: "success" | "error") => void;
}) {
  interface LiveStreamSnapshot {
    detectedFeatureIds: number[];
    insights: RuntimeInsight[];
    messages: ConversationMessage[];
    runtimeState: RuntimeSessionState | null;
    sessionId: string;
    stages: RuntimeStage[];
  }

  const activeStreamRef = useRef<{
    abortController: AbortController;
    assistantMessageId: string;
    liveTurnId: string;
    serverTurnId?: string;
    sessionId: string;
    userMessageId: string;
  } | null>(null);
  const activeStreamSnapshotRef = useRef<LiveStreamSnapshot | null>(null);

  function restoreActiveStreamSnapshot(sessionId: string) {
    const snapshot = activeStreamSnapshotRef.current;
    if (!snapshot || snapshot.sessionId !== sessionId) {
      return false;
    }
    setMessages(snapshot.messages);
    setInsights(snapshot.insights);
    setStages(snapshot.stages);
    setRuntimeState(snapshot.runtimeState);
    setDetectedFeatureIds(snapshot.detectedFeatureIds);
    messagesSessionIdRef.current = sessionId;
    return true;
  }

  function updateActiveStreamSnapshot(
    sessionId: string,
    updater: (snapshot: LiveStreamSnapshot) => LiveStreamSnapshot,
  ) {
    const snapshot = activeStreamSnapshotRef.current;
    if (!snapshot || snapshot.sessionId !== sessionId) {
      return;
    }
    activeStreamSnapshotRef.current = updater(snapshot);
  }

  function applyActiveStreamSnapshotIfVisible(sessionId: string) {
    if (messagesSessionIdRef.current === sessionId) {
      restoreActiveStreamSnapshot(sessionId);
    }
  }

  async function rollbackActiveStream() {
    const active = activeStreamRef.current;
    if (!active) {
      return;
    }
    setMessages((current) =>
      current.filter(
        (message) =>
          message.id !== active.userMessageId &&
          message.id !== active.assistantMessageId,
      ),
    );
    setInsights((current) =>
      current.filter((insight) => insight.turnId !== active.liveTurnId),
    );
    setStages(createInitialStages());
    activeStreamSnapshotRef.current = null;
    setActiveStreamingSessionId(null);
    if (active.serverTurnId) {
      await abortSessionTurn(active.sessionId, active.serverTurnId);
    }
    void queryClient.invalidateQueries({
      queryKey: sessionTurnsQueryKey(active.sessionId),
    });
    void queryClient.invalidateQueries({
      queryKey: sessionTracesQueryKey(active.sessionId),
    });
  }

  function cancelMessage() {
    if (!activeStreamRef.current) {
      return;
    }
    showActionNotice("已停止生成");
    activeStreamRef.current.abortController.abort();
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content) {
      return;
    }
    if (isStreaming) {
      showActionNotice(
        "当前已有会话正在生成，请等待完成或切回该会话停止生成。",
        "error",
      );
      return;
    }

    let target = selected;
    if (!target) {
      try {
        await queryClient.cancelQueries({ queryKey: ["sessions"] });
        target = await createSession("新的研发会话");
        setSelectedId(target.id);
        rememberSession(target);
      } catch (error) {
        showActionNotice(`创建默认会话失败：${messageFromError(error)}`, "error");
        return;
      }
    }

    const userMessageId = `msg_user_${Date.now()}`;
    const assistantMessageId = `msg_assistant_${Date.now()}`;
    const liveTurnId = `live_${assistantMessageId}`;
    const clientTurnId = createClientTurnId();
    const abortController = new AbortController();
    const leakGuard = createReasoningLeakGuard("mask_in_ui");
    const nextMessages = [
      ...messages,
      { id: userMessageId, role: "user" as const, content },
      {
        id: assistantMessageId,
        role: "assistant" as const,
        content: "",
        status: "streaming" as const,
      },
    ];
    activeStreamRef.current = {
      abortController,
      assistantMessageId,
      liveTurnId,
      serverTurnId: clientTurnId,
      sessionId: target.id,
      userMessageId,
    };
    activeStreamSnapshotRef.current = {
      detectedFeatureIds: [],
      insights,
      messages: nextMessages,
      runtimeState,
      sessionId: target.id,
      stages: createInitialStages(),
    };
    setDraft("");
    setStages(activeStreamSnapshotRef.current.stages);
    setDetectedFeatureIds([]);
    setIsStreaming(true);
    setActiveStreamingSessionId(target.id);
    messagesSessionIdRef.current = target.id;
    setMessages(nextMessages);

    try {
      await streamSessionMessage({
        sessionId: target.id,
        content,
        client_turn_id: clientTurnId,
        signal: abortController.signal,
        onTurnId: (turnId) => {
          if (activeStreamRef.current?.liveTurnId === liveTurnId) {
            activeStreamRef.current = {
              ...activeStreamRef.current,
              serverTurnId: turnId,
            };
          }
        },
        onEvent: (event) => {
          const isVisibleTargetSession = messagesSessionIdRef.current === target.id;
          updateActiveStreamSnapshot(target.id, (snapshot) => ({
            ...snapshot,
            stages: reduceStages(snapshot.stages, event),
          }));
          if (event.type === "runtime_state") {
            const runtimeState = runtimeStateFromEvent(event);
            if (runtimeState) {
              updateActiveStreamSnapshot(target.id, (snapshot) => ({
                ...snapshot,
                runtimeState,
              }));
            }
          }
          const insight = runtimeInsightFromEvent(event);
          if (insight) {
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              insights: appendRuntimeInsight(snapshot.insights, {
                ...insight,
                occurredAt: new Date().toISOString(),
                turnId: liveTurnId,
              }),
            }));
          }
          if (event.type === "scope_detection") {
            const ids = featureIdsFromEvent(event.data);
            if (ids.length > 0) {
              updateActiveStreamSnapshot(target.id, (snapshot) => ({
                ...snapshot,
                detectedFeatureIds: [
                  ...new Set([...ids, ...snapshot.detectedFeatureIds]),
                ],
              }));
            }
          }
          const delta = textDeltaFromEvent(event);
          if (delta) {
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              insights: removeOpencodeRunningInsight(snapshot.insights, liveTurnId),
            }));
            const guarded = leakGuard.feed(delta);
            if (guarded.diagnostic) {
              const leakInsight = runtimeInsightFromEvent({
                type: guarded.diagnostic.type,
                data: { ...guarded.diagnostic },
              });
              if (leakInsight) {
                updateActiveStreamSnapshot(target.id, (snapshot) => ({
                  ...snapshot,
                  insights: appendRuntimeInsight(snapshot.insights, {
                    ...leakInsight,
                    occurredAt: new Date().toISOString(),
                    turnId: liveTurnId,
                  }),
                }));
              }
            }
            if (!guarded.visibleText) {
              applyActiveStreamSnapshotIfVisible(target.id);
              return;
            }
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              messages: snapshot.messages.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: `${message.content}${guarded.visibleText}`,
                    }
                  : message,
              ),
            }));
          }
          const askUserMessage = askUserMessageFromEvent(event);
          if (askUserMessage) {
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              insights: removeOpencodeRunningInsight(snapshot.insights, liveTurnId),
            }));
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              messages: snapshot.messages.map((message) =>
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
            }));
          }
          if (event.type === "error") {
            const errorMessage =
              typeof event.data.message === "string"
                ? event.data.message
                : typeof event.data.error === "string"
                  ? event.data.error
                  : "未知错误";
            showActionNotice(
              `Agent 运行失败：${errorMessage}`,
              "error",
            );
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              insights: removeOpencodeRunningInsight(snapshot.insights, liveTurnId),
            }));
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              messages: snapshot.messages.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      content: errorMessage,
                      status: "error",
                    }
                  : message,
              ),
            }));
          }
          if (event.type === "done") {
            const turnId =
              typeof event.data.turn_id === "string"
                ? event.data.turn_id
                : null;
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              insights: removeOpencodeRunningInsight(snapshot.insights, liveTurnId),
            }));
            if (turnId) {
              updateActiveStreamSnapshot(target.id, (snapshot) => ({
                ...snapshot,
                insights: snapshot.insights.map((insight) =>
                  insight.turnId === liveTurnId
                    ? { ...insight, turnId }
                    : insight,
                ),
              }));
            }
            updateActiveStreamSnapshot(target.id, (snapshot) => ({
              ...snapshot,
              messages: snapshot.messages.map((message) =>
                message.id === assistantMessageId
                  ? {
                      ...message,
                      status: "done",
                      turnId: turnId ?? message.turnId,
                    }
                  : message,
              ),
            }));
          }
          if (!isVisibleTargetSession) {
            return;
          }
          applyActiveStreamSnapshotIfVisible(target.id);
        },
      });
      void queryClient.invalidateQueries({
        queryKey: sessionTurnsQueryKey(target.id),
      });
      void queryClient.invalidateQueries({
        queryKey: sessionTracesQueryKey(target.id),
      });
      refreshSessionListAfterTitleGeneration(queryClient, {
        sessionId: target.id,
        rememberSession,
      });
    } catch (error) {
      if (isAbortError(error)) {
        try {
          await rollbackActiveStream();
          showActionNotice("已停止生成");
        } catch (rollbackError) {
          showActionNotice(`停止生成失败：${messageFromError(rollbackError)}`, "error");
        }
        return;
      }
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantMessageId
            ? { ...message, content: messageFromError(error), status: "error" }
            : message,
        ),
      );
      showActionNotice(`会话请求失败：${messageFromError(error)}`, "error");
      setStages((current) =>
        current.map((stage) =>
          stage.status === "active" ? { ...stage, status: "error" } : stage,
        ),
      );
    } finally {
      if (activeStreamRef.current?.sessionId === target.id) {
        applyActiveStreamSnapshotIfVisible(target.id);
      }
      setIsStreaming(false);
      setActiveStreamingSessionId(null);
      activeStreamRef.current = null;
    }
  }

  return { cancelMessage, restoreActiveStreamSnapshot, sendMessage };
}

export function refreshSessionListAfterTitleGeneration(
  queryClient: QueryClient,
  options: {
    sessionId?: string;
    rememberSession?: (session: SessionResponse) => void;
    generateSessionTitle?: (sessionId: string) => Promise<SessionResponse>;
  } = {},
) {
  void queryClient.invalidateQueries({ queryKey: ["sessions"] });
  if (options.sessionId && options.rememberSession) {
    const requestTitle = options.generateSessionTitle ?? generateSessionTitle;
    void requestTitle(options.sessionId)
      .then((session) => {
        options.rememberSession?.(session);
      })
      .catch(() => undefined);
  }
  for (const delayMs of [1_500, 5_000, 12_000]) {
    window.setTimeout(() => {
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    }, delayMs);
  }
}

function isAbortError(error: unknown) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return true;
  }
  return error instanceof Error && error.name === "AbortError";
}

function createClientTurnId() {
  const suffix = Math.random().toString(36).slice(2, 10);
  return `turn_client_${Date.now()}_${suffix}`;
}
