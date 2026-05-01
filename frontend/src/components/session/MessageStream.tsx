import { Minus, SquareActivity, ThumbsDown, ThumbsUp } from "lucide-react";

import type { FeedbackVerdict } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import type { ConversationMessage } from "./session-model";

interface MessageStreamProps {
  messages: ConversationMessage[];
  feedbackByTurnId?: Record<string, FeedbackVerdict>;
  feedbackPendingTurnId?: string | null;
  onFeedback?: (turnId: string, verdict: FeedbackVerdict) => void;
}

const FEEDBACK_LABELS: Record<FeedbackVerdict, string> = {
  solved: "已解决",
  partial: "部分解决",
  wrong: "没解决"
};

export function MessageStream({
  messages,
  feedbackByTurnId = {},
  feedbackPendingTurnId = null,
  onFeedback
}: MessageStreamProps) {
  if (messages.length === 0) {
    return (
      <div className="message-stream">
        <div className="assistant-message">
          <SquareActivity aria-hidden="true" size={18} />
          <div>
            <strong>等待输入</strong>
            <p>这里会显示会话消息、LLM 输出、证据引用和需要用户补充的问题。</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="message-stream">
      {messages.map((message) => (
        <article className="message-bubble" data-role={message.role} key={message.id}>
          <div className="message-meta">{message.role === "user" ? "你" : message.role === "assistant" ? "CodeAsk" : "系统"}</div>
          <p>{message.content || "正在生成..."}</p>
          {message.role === "assistant" && message.status === "done" && message.turnId ? (
            <FeedbackBar
              current={feedbackByTurnId[message.turnId]}
              disabled={feedbackPendingTurnId === message.turnId}
              onFeedback={(verdict) => onFeedback?.(message.turnId ?? "", verdict)}
            />
          ) : null}
        </article>
      ))}
    </div>
  );
}

function FeedbackBar({
  current,
  disabled,
  onFeedback
}: {
  current?: FeedbackVerdict;
  disabled: boolean;
  onFeedback: (verdict: FeedbackVerdict) => void;
}) {
  if (current) {
    return (
      <div className="message-feedback" aria-label="回答反馈">
        <Badge>已反馈 · {FEEDBACK_LABELS[current]}</Badge>
      </div>
    );
  }

  return (
    <div className="message-feedback" aria-label="回答反馈">
      <span>这次回答是否解决问题？</span>
      <Button
        disabled={disabled}
        icon={<ThumbsUp aria-hidden="true" size={14} />}
        onClick={() => onFeedback("solved")}
        type="button"
        variant="quiet"
      >
        已解决
      </Button>
      <Button
        disabled={disabled}
        icon={<Minus aria-hidden="true" size={14} />}
        onClick={() => onFeedback("partial")}
        type="button"
        variant="quiet"
      >
        部分解决
      </Button>
      <Button
        disabled={disabled}
        icon={<ThumbsDown aria-hidden="true" size={14} />}
        onClick={() => onFeedback("wrong")}
        type="button"
        variant="quiet"
      >
        没解决
      </Button>
    </div>
  );
}
