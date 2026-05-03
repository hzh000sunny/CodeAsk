import type { RefObject } from "react";

import type {
  FeedbackVerdict,
  SessionResponse,
} from "../../types/api";
import { MessageStream } from "./MessageStream";
import { SessionComposer } from "./SessionComposer";
import { SessionHeader } from "./SessionHeader";
import { copyTextToClipboard } from "./session-clipboard";
import type { ConversationMessage } from "./session-model";

interface SessionConversationPanelProps {
  actionNotice: string;
  copiedSessionId: string | null;
  createPending: boolean;
  draft: string;
  feedbackByTurnId: Record<string, FeedbackVerdict>;
  feedbackPendingTurnId: string | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  forceCodeInvestigation: boolean;
  isStreaming: boolean;
  messages: ConversationMessage[];
  onCopySessionId: () => void;
  onDraftChange: (value: string) => void;
  onFeedback: (payload: {
    sessionId: string;
    turnId: string;
    verdict: FeedbackVerdict;
  }) => void;
  onForceCodeInvestigationChange: (checked: boolean) => void;
  onOpenReportDialog: () => void;
  onSendMessage: () => void;
  onUnsupportedAction: (message: string) => void;
  onUploadFile: (file: File | undefined) => void;
  reportPending: boolean;
  selected: SessionResponse | null;
  selectedSessionId: string;
  uploadStatus: string;
}

export function SessionConversationPanel({
  actionNotice,
  copiedSessionId,
  createPending,
  draft,
  feedbackByTurnId,
  feedbackPendingTurnId,
  fileInputRef,
  forceCodeInvestigation,
  isStreaming,
  messages,
  onCopySessionId,
  onDraftChange,
  onFeedback,
  onForceCodeInvestigationChange,
  onOpenReportDialog,
  onSendMessage,
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
        forceCodeInvestigation={forceCodeInvestigation}
        isStreaming={isStreaming}
        onDraftChange={onDraftChange}
        onForceCodeInvestigationChange={onForceCodeInvestigationChange}
        onOpenReportDialog={onOpenReportDialog}
        onSendMessage={onSendMessage}
        onUploadFile={onUploadFile}
        reportPending={reportPending}
        selected={Boolean(selected)}
        uploadStatus={uploadStatus}
      />
    </section>
  );
}
