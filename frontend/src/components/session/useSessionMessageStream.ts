import { useRef, type Dispatch, type RefObject, type SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";

import { abortSessionTurn, createSession } from "../../lib/api";
import { streamSessionMessage } from "../../lib/sse";
import type { SessionResponse } from "../../types/api";
import {
  sessionTracesQueryKey,
  sessionTurnsQueryKey,
} from "./session-cache";
import { featureIdsFromEvent } from "./session-history";
import {
  askUserMessageFromEvent,
  createInitialStages,
  messageFromError,
  reduceStages,
  runtimeInsightFromEvent,
  textDeltaFromEvent,
  type ConversationMessage,
  type RuntimeInsight,
  type RuntimeStage,
} from "./session-model";

export function useSessionMessageStream({
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
}: {
  draft: string;
  forceCodeInvestigation: boolean;
  isStreaming: boolean;
  messagesSessionIdRef: RefObject<string | null>;
  queryClient: QueryClient;
  rememberSession: (session: SessionResponse) => void;
  selected: SessionResponse | null;
  setDetectedFeatureIds: Dispatch<SetStateAction<number[]>>;
  setDraft: Dispatch<SetStateAction<string>>;
  setInsights: Dispatch<SetStateAction<RuntimeInsight[]>>;
  setIsStreaming: Dispatch<SetStateAction<boolean>>;
  setMessages: Dispatch<SetStateAction<ConversationMessage[]>>;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  setStages: Dispatch<SetStateAction<RuntimeStage[]>>;
  showActionNotice: (message: string) => void;
}) {
  const activeStreamRef = useRef<{
    abortController: AbortController;
    assistantMessageId: string;
    liveTurnId: string;
    serverTurnId?: string;
    sessionId: string;
    userMessageId: string;
  } | null>(null);

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
    const liveTurnId = `live_${assistantMessageId}`;
    const clientTurnId = createClientTurnId();
    const abortController = new AbortController();
    activeStreamRef.current = {
      abortController,
      assistantMessageId,
      liveTurnId,
      serverTurnId: clientTurnId,
      sessionId: target.id,
      userMessageId,
    };
    setDraft("");
    setStages(createInitialStages());
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
        client_turn_id: clientTurnId,
        force_code_investigation: forceCodeInvestigation,
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
          setStages((current) => reduceStages(current, event));
          const insight = runtimeInsightFromEvent(event);
          if (insight) {
            setInsights((current) => [
              ...current,
              {
                ...insight,
                occurredAt: new Date().toISOString(),
                turnId: liveTurnId,
              },
            ]);
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
            showActionNotice(
              `Agent 运行失败：${String(event.data.message ?? "未知错误")}`,
            );
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
            if (turnId) {
              setInsights((current) =>
                current.map((insight) =>
                  insight.turnId === liveTurnId
                    ? { ...insight, turnId }
                    : insight,
                ),
              );
            }
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
      if (isAbortError(error)) {
        try {
          await rollbackActiveStream();
          showActionNotice("已停止生成");
        } catch (rollbackError) {
          showActionNotice(`停止生成失败：${messageFromError(rollbackError)}`);
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
      showActionNotice(`会话请求失败：${messageFromError(error)}`);
      setStages((current) =>
        current.map((stage) =>
          stage.status === "active" ? { ...stage, status: "error" } : stage,
        ),
      );
    } finally {
      setIsStreaming(false);
      activeStreamRef.current = null;
    }
  }

  return { cancelMessage, sendMessage };
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
