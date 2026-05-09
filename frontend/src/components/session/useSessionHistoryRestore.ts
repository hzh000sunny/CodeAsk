import {
  useEffect,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";

import type { AgentTraceResponse, SessionTurnResponse } from "../../types/api";
import {
  featureIdsFromSessionTraces,
  insightsFromSessionHistory,
  messagesFromSessionTurns,
  stagesFromSessionTraces,
} from "./session-history";
import { createInitialStages } from "./session-model";
import type {
  ConversationMessage,
  RuntimeInsight,
  RuntimeStage,
} from "./session-model";

export function useSessionHistoryRestore({
  appliedHistoryKeyRef,
  hasLoadedSessionTraces,
  hasLoadedSessionTurns,
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
  setDetectedFeatureIds,
  setStages,
  stages,
}: {
  appliedHistoryKeyRef: RefObject<string | null>;
  hasLoadedSessionTraces: boolean;
  hasLoadedSessionTurns: boolean;
  insights: RuntimeInsight[];
  isStreaming: boolean;
  messages: ConversationMessage[];
  messagesSessionIdRef: RefObject<string | null>;
  selectedSessionId: string;
  sessionTraces: AgentTraceResponse[];
  sessionTracesUpdatedAt: number;
  sessionTurns: SessionTurnResponse[];
  sessionTurnsUpdatedAt: number;
  setInsights: Dispatch<SetStateAction<RuntimeInsight[]>>;
  setMessages: (value: ConversationMessage[] | ((current: ConversationMessage[]) => ConversationMessage[])) => void;
  setDetectedFeatureIds: Dispatch<SetStateAction<number[]>>;
  setStages: (value: RuntimeStage[] | ((current: RuntimeStage[]) => RuntimeStage[])) => void;
  stages: RuntimeStage[];
}) {
  useEffect(() => {
    if (!selectedSessionId) {
      if (!isStreaming) {
        setMessages((current) => (current.length === 0 ? current : []));
      }
      setInsights((current) => (current.length === 0 ? current : []));
      setDetectedFeatureIds((current) => (current.length === 0 ? current : []));
      setStages((current) =>
        current.some((stage) => stage.status !== "pending")
          ? createInitialStages()
          : current,
      );
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
    setDetectedFeatureIds(featureIdsFromSessionTraces(sessionTraces));
    setStages(stagesFromSessionTraces(sessionTraces));
    messagesSessionIdRef.current = selectedSessionId;
    appliedHistoryKeyRef.current = historyKey;
  }, [
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
    setDetectedFeatureIds,
    setStages,
    stages,
  ]);
}
