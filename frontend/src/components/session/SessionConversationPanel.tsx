import type { RefObject } from "react";

import type {
  FeedbackVerdict,
  SessionResponse,
} from "../../types/api";
import type { ActionTraceEvent } from "./action-trace/action-trace-model";
import { MessageStream } from "./MessageStream";
import { SessionComposer } from "./SessionComposer";
import { SessionHeader } from "./SessionHeader";
import { copyTextToClipboard } from "./session-clipboard";
import type { ConversationMessage } from "./session-model";

interface SessionConversationPanelProps {
  copiedSessionId: string | null;
  createPending: boolean;
  draft: string;
  feedbackByTurnId: Record<string, FeedbackVerdict>;
  feedbackPendingTurnId: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  insights: ActionTraceEvent[];
  isStreaming: boolean;
  messages: ConversationMessage[];
  onCancelMessage: () => void;
  onCopySessionId: () => void;
  onDraftChange: (value: string) => void;
  onFeedback: (payload: {
    sessionId: string;
    turnId: string;
    verdict: FeedbackVerdict;
  }) => void;
  onOpenReportDialog: () => void;
  onSendMessage: () => void;
  onUploadClick: () => void;
  onUnsupportedAction: (message: string) => void;
  onUploadFile: (file: File | undefined) => void;
  reportPending: boolean;
  selected: SessionResponse | null;
  selectedSessionId: string;
  uploadStatus: string;
}

export function SessionConversationPanel({
  copiedSessionId,
  createPending,
  draft,
  feedbackByTurnId,
  feedbackPendingTurnId,
  fileInputRef,
  insights,
  isStreaming,
  messages,
  onCancelMessage,
  onCopySessionId,
  onDraftChange,
  onFeedback,
  onOpenReportDialog,
  onSendMessage,
  onUploadClick,
  onUnsupportedAction,
  onUploadFile,
  reportPending,
  selected,
  selectedSessionId,
  uploadStatus,
}: SessionConversationPanelProps) {
  return (
    <section
      className="conversation-panel"
      role="region"
      aria-label="会话消息"
    >
      <SessionHeader
        copiedSessionId={copiedSessionId}
        onCopySessionId={onCopySessionId}
        selected={selected}
      />

      <MessageStream
        feedbackByTurnId={feedbackByTurnId}
        feedbackPendingTurnId={feedbackPendingTurnId}
        insights={insights}
        messages={messages}
        onCopyCode={(code) => copyTextToClipboard(code)}
        onCopyMessage={(message) => copyTextToClipboard(message.content)}
        onFeedback={(turnId, verdict) => {
          onFeedback({
            sessionId: selectedSessionId,
            turnId,
            verdict,
          });
        }}
        onUnsupportedAction={onUnsupportedAction}
      />

      <SessionComposer
        createPending={createPending}
        draft={draft}
        fileInputRef={fileInputRef}
        isStreaming={isStreaming}
        onDraftChange={onDraftChange}
        onOpenReportDialog={onOpenReportDialog}
        onCancelMessage={onCancelMessage}
        onSendMessage={onSendMessage}
        onUploadClick={onUploadClick}
        onUploadFile={onUploadFile}
        reportPending={reportPending}
        selected={Boolean(selected)}
        uploadStatus={uploadStatus}
      />
    </section>
  );
}
