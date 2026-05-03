import type { Dispatch, RefObject, SetStateAction } from "react";
import type { QueryClient } from "@tanstack/react-query";

import { createSession } from "../../lib/api";
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

  return { sendMessage };
}
