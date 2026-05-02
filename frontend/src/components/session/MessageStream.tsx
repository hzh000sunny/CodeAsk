import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Copy,
  Minus,
  RotateCcw,
  Share2,
  SquareActivity,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import type { FeedbackVerdict } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import type { ConversationMessage } from "./session-model";

interface MessageStreamProps {
  messages: ConversationMessage[];
  feedbackByTurnId?: Record<string, FeedbackVerdict>;
  feedbackPendingTurnId?: string | null;
  onCopyCode?: (code: string) => Promise<void> | void;
  onCopyMessage?: (message: ConversationMessage) => Promise<void> | void;
  onFeedback?: (turnId: string, verdict: FeedbackVerdict) => void;
  onUnsupportedAction?: (label: string) => void;
}

const FEEDBACK_LABELS: Record<FeedbackVerdict, string> = {
  solved: "已解决",
  partial: "部分解决",
  wrong: "没解决",
};

export function MessageStream({
  messages,
  feedbackByTurnId = {},
  feedbackPendingTurnId = null,
  onCopyCode,
  onCopyMessage,
  onFeedback,
  onUnsupportedAction,
}: MessageStreamProps) {
  const streamRef = useRef<HTMLDivElement | null>(null);
  const copyToastTimeoutRef = useRef<number | null>(null);
  const [copyStatus, setCopyStatus] = useState<{
    messageId: string;
    label: string;
  } | null>(null);

  useLayoutEffect(() => {
    const stream = streamRef.current;
    if (!stream) {
      return;
    }
    stream.scrollTop = stream.scrollHeight;
  }, [messages]);

  useEffect(() => {
    return () => {
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
    };
  }, []);

  function showCopyStatus(messageId: string, label: string) {
    if (copyToastTimeoutRef.current) {
      window.clearTimeout(copyToastTimeoutRef.current);
    }
    setCopyStatus({ messageId, label });
    copyToastTimeoutRef.current = window.setTimeout(() => {
      setCopyStatus(null);
      copyToastTimeoutRef.current = null;
    }, 1200);
  }

  async function copyMessage(message: ConversationMessage) {
    try {
      await onCopyMessage?.(message);
      showCopyStatus(message.id, "已复制");
    } catch {
      showCopyStatus(message.id, "复制失败");
    }
  }

  if (messages.length === 0) {
    return (
      <div className="message-stream" ref={streamRef}>
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
    <div className="message-stream" ref={streamRef}>
      {messages.map((message) => (
        <article
          className="message-bubble"
          data-role={message.role}
          key={message.id}
        >
          {message.content ? (
            <MarkdownRenderer
              content={message.content}
              onCopyCode={onCopyCode}
            />
          ) : (
            <p className="streaming-placeholder">正在生成...</p>
          )}
          <div className="message-actions" aria-label="消息操作">
            <button
              aria-label={`复制 ${messageRoleLabel(message)} 消息`}
              onClick={() => void copyMessage(message)}
              title="复制"
              type="button"
            >
              <Copy aria-hidden="true" size={15} />
            </button>
            {copyStatus?.messageId === message.id ? (
              <span className="message-action-toast" role="status">
                {copyStatus.label}
              </span>
            ) : null}
            <button
              aria-label={`重新生成 ${messageRoleLabel(message)} 消息`}
              onClick={() => onUnsupportedAction?.("重新生成暂不支持")}
              title="重新生成"
              type="button"
            >
              <RotateCcw aria-hidden="true" size={15} />
            </button>
            <button
              aria-label={`分享 ${messageRoleLabel(message)} 消息`}
              onClick={() => onUnsupportedAction?.("分享暂不支持")}
              title="分享"
              type="button"
            >
              <Share2 aria-hidden="true" size={15} />
            </button>
          </div>
          {message.role === "assistant" &&
          message.status === "done" &&
          message.turnId ? (
            <FeedbackBar
              current={feedbackByTurnId[message.turnId]}
              disabled={feedbackPendingTurnId === message.turnId}
              onFeedback={(verdict) =>
                onFeedback?.(message.turnId ?? "", verdict)
              }
            />
          ) : null}
        </article>
      ))}
      <div aria-hidden="true" data-scroll-anchor="bottom" />
    </div>
  );
}

function messageRoleLabel(message: ConversationMessage) {
  if (message.role === "user") {
    return "你";
  }
  if (message.role === "assistant") {
    return "CodeAsk";
  }
  return "系统";
}

function FeedbackBar({
  current,
  disabled,
  onFeedback,
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
