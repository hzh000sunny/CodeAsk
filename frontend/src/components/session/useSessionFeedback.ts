import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { postFeedback, postFrontendEvent } from "../../lib/api";
import type { FeedbackVerdict } from "../../types/api";
import { feedbackLabel } from "./session-feedback";
import { messageFromError } from "./session-model";

export function useSessionFeedback({
  showActionNotice,
}: {
  showActionNotice: (message: string) => void;
}) {
  const [feedbackByTurnId, setFeedbackByTurnId] = useState<
    Record<string, FeedbackVerdict>
  >({});
  const [feedbackPendingTurnId, setFeedbackPendingTurnId] = useState<
    string | null
  >(null);
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

  function submitFeedback({
    sessionId,
    turnId,
    verdict,
  }: {
    sessionId: string;
    turnId: string;
    verdict: FeedbackVerdict;
  }) {
    if (!sessionId || feedbackPendingTurnId === turnId || feedbackByTurnId[turnId]) {
      return;
    }
    feedbackMutation.mutate({ sessionId, turnId, verdict });
  }

  return {
    feedbackByTurnId,
    feedbackPendingTurnId,
    submitFeedback,
  };
}
