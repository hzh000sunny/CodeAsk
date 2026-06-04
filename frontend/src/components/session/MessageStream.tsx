import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Copy,
  Minus,
  RotateCcw,
  Share2,
  Telescope,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import type { FeedbackVerdict } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import type { ActionTraceEvent } from "./action-trace/action-trace-model";
import type { ConversationMessage } from "./session-model";
import { WorkingTimeline } from "./WorkingTimeline";

interface MessageStreamProps {
  messages: ConversationMessage[];
  insights?: ActionTraceEvent[];
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

const EXAMPLE_PROMPTS = [
  "这个接口偶发 401，是鉴权中间件的问题吗？",
  "帮我定位这段报错日志最可能的根因。",
  "最近这个行为是从哪个提交引入的？",
];

const SCROLL_STICK_THRESHOLD = 120;

export function MessageStream({
  messages,
  insights = [],
  feedbackByTurnId = {},
  feedbackPendingTurnId = null,
  onCopyCode,
  onCopyMessage,
  onFeedback,
  onUnsupportedAction,
}: MessageStreamProps) {
  const streamRef = useRef<HTMLDivElement | null>(null);
  const stickToBottomRef = useRef(true);
  const lastLengthRef = useRef(messages.length);
  const copyToastTimeoutRef = useRef<number | null>(null);
  const [copyStatus, setCopyStatus] = useState<{
    messageId: string;
    label: string;
  } | null>(null);

  function handleScroll() {
    const stream = streamRef.current;
    if (!stream) {
      return;
    }
    const distanceFromBottom =
      stream.scrollHeight - stream.scrollTop - stream.clientHeight;
    stickToBottomRef.current = distanceFromBottom < SCROLL_STICK_THRESHOLD;
  }

  useLayoutEffect(() => {
    const stream = streamRef.current;
    if (!stream) {
      return;
    }
    // A new turn (the list grew) always snaps to the bottom; while a single
    // turn streams (length unchanged, content grows) we only follow if the
    // reader is already near the bottom, so scrolling up to re-read sticks.
    if (messages.length !== lastLengthRef.current) {
      stickToBottomRef.current = true;
      lastLengthRef.current = messages.length;
    }
    if (stickToBottomRef.current) {
      stream.scrollTop = stream.scrollHeight;
    }
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
      <div className="message-stream transcript" ref={streamRef}>
        <div className="transcript-empty">
          <span className="transcript-empty-mark" aria-hidden="true">
            <Telescope size={22} />
          </span>
          <h2>开始一次代码调查</h2>
          <p>
            描述你遇到的问题，或粘贴关键日志片段。CodeAsk
            会检索 Wiki、问题报告与代码仓库，并把调查过程实时展示在这里。
          </p>
          <ul className="transcript-empty-prompts">
            {EXAMPLE_PROMPTS.map((prompt) => (
              <li key={prompt}>{prompt}</li>
            ))}
          </ul>
        </div>
      </div>
    );
  }

  const precedingUserIdByMessageId = mapPrecedingUserIds(messages);

  return (
    <div
      className="message-stream transcript"
      onScroll={handleScroll}
      ref={streamRef}
    >
      {messages.map((message) => {
        if (message.role === "user") {
          return (
            <UserTurn
              copyLabel={
                copyStatus?.messageId === message.id ? copyStatus.label : null
              }
              key={message.id}
              message={message}
              onCopy={() => void copyMessage(message)}
            />
          );
        }

        const turnInsights = insightsForTurn(
          message,
          precedingUserIdByMessageId[message.id],
          insights,
        );
        return (
          <AssistantTurn
            copyLabel={
              copyStatus?.messageId === message.id ? copyStatus.label : null
            }
            feedback={message.turnId ? feedbackByTurnId[message.turnId] : undefined}
            feedbackPending={
              Boolean(message.turnId) &&
              feedbackPendingTurnId === message.turnId
            }
            insights={turnInsights}
            key={message.id}
            message={message}
            onCopy={() => void copyMessage(message)}
            onCopyCode={onCopyCode}
            onFeedback={(verdict) => onFeedback?.(message.turnId ?? "", verdict)}
            onUnsupportedAction={onUnsupportedAction}
          />
        );
      })}
      <div aria-hidden="true" data-scroll-anchor="bottom" />
    </div>
  );
}

function UserTurn({
  copyLabel,
  message,
  onCopy,
}: {
  copyLabel: string | null;
  message: ConversationMessage;
  onCopy: () => void;
}) {
  return (
    <article className="turn turn-user" data-role="user" key={message.id}>
      <div className="turn-user-card">
        <p className="plain-message-content">{message.content}</p>
      </div>
      <div className="turn-actions" aria-label="消息操作">
        {copyLabel ? (
          <span className="message-action-toast" role="status">
            {copyLabel}
          </span>
        ) : null}
        <button
          aria-label="复制你的消息"
          onClick={onCopy}
          title="复制"
          type="button"
        >
          <Copy aria-hidden="true" size={15} />
        </button>
      </div>
    </article>
  );
}

function AssistantTurn({
  copyLabel,
  feedback,
  feedbackPending,
  insights,
  message,
  onCopy,
  onCopyCode,
  onFeedback,
  onUnsupportedAction,
}: {
  copyLabel: string | null;
  feedback?: FeedbackVerdict;
  feedbackPending: boolean;
  insights: ActionTraceEvent[];
  message: ConversationMessage;
  onCopy: () => void;
  onCopyCode?: (code: string) => Promise<void> | void;
  onFeedback: (verdict: FeedbackVerdict) => void;
  onUnsupportedAction?: (label: string) => void;
}) {
  const isStreaming = message.status === "streaming";

  return (
    <article
      className="turn turn-assistant"
      data-role="assistant"
      data-streaming={isStreaming ? "true" : "false"}
    >
      <div className="turn-gutter" aria-hidden="true">
        <span className="turn-avatar" data-live={isStreaming ? "true" : "false"}>
          CA
        </span>
        <span className="turn-thread" />
      </div>
      <div className="turn-body">
        <div className="turn-head">
          <span className="turn-author">CodeAsk</span>
          {message.stoppedAt ? (
            <span
              className="turn-stopped"
              title={`停止时间：${formatStoppedAt(message.stoppedAt)}`}
            >
              <Badge>已停止</Badge>
            </span>
          ) : null}
        </div>

        <WorkingTimeline events={insights} live={isStreaming} />

        {message.content ? (
          <div className="turn-content">
            <MarkdownRenderer content={message.content} onCopyCode={onCopyCode} />
            {isStreaming ? (
              <span aria-hidden="true" className="stream-caret" />
            ) : null}
          </div>
        ) : isStreaming ? (
          <p className="streaming-placeholder">
            <span aria-hidden="true" className="stream-caret" />
          </p>
        ) : message.stoppedAt ? (
          <p className="streaming-placeholder">用户在模型回复前停止了这一轮</p>
        ) : (
          <p className="streaming-placeholder">正在生成...</p>
        )}

        <div className="turn-footer">
          <div className="turn-actions" aria-label="消息操作">
            {copyLabel ? (
              <span className="message-action-toast" role="status">
                {copyLabel}
              </span>
            ) : null}
            <button
              aria-label="复制 CodeAsk 消息"
              onClick={onCopy}
              title="复制"
              type="button"
            >
              <Copy aria-hidden="true" size={15} />
            </button>
            <button
              aria-label="重新生成 CodeAsk 消息"
              onClick={() => onUnsupportedAction?.("重新生成暂不支持")}
              title="重新生成"
              type="button"
            >
              <RotateCcw aria-hidden="true" size={15} />
            </button>
            <button
              aria-label="分享 CodeAsk 消息"
              onClick={() => onUnsupportedAction?.("分享暂不支持")}
              title="分享"
              type="button"
            >
              <Share2 aria-hidden="true" size={15} />
            </button>
          </div>
          {message.status === "done" && message.turnId ? (
            <FeedbackBar
              current={feedback}
              disabled={feedbackPending}
              onFeedback={onFeedback}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
}

/** Map each assistant message to the id of the user message that precedes it. */
function mapPrecedingUserIds(
  messages: ConversationMessage[],
): Record<string, string | undefined> {
  const result: Record<string, string | undefined> = {};
  let cursor: string | undefined;
  for (const message of messages) {
    if (message.role === "user") {
      cursor = message.id;
    } else {
      result[message.id] = cursor;
    }
  }
  return result;
}

/**
 * Collect the action-trace events belonging to one assistant turn. The join
 * has to survive three id regimes: a live streaming turn (insights keyed by
 * `live_<assistantMessageId>`), a freshly-finished turn (migrated to the
 * server turn id, which also lands on `message.turnId`), and a reloaded turn
 * (traces keyed by the *user* turn id — i.e. the preceding user message id —
 * because the persisted agent turn row gets its own unrelated id).
 */
function insightsForTurn(
  message: ConversationMessage,
  precedingUserMessageId: string | undefined,
  insights: ActionTraceEvent[],
): ActionTraceEvent[] {
  if (insights.length === 0) {
    return [];
  }
  const keys = new Set<string>();
  if (message.turnId) {
    keys.add(message.turnId);
  }
  keys.add(`live_${message.id}`);
  if (precedingUserMessageId) {
    keys.add(precedingUserMessageId);
  }
  return insights.filter(
    (insight) => insight.turnId !== undefined && keys.has(insight.turnId),
  );
}

function formatStoppedAt(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
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
