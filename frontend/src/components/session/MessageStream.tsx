import { SquareActivity } from "lucide-react";

import type { ConversationMessage } from "./session-model";

interface MessageStreamProps {
  messages: ConversationMessage[];
}

export function MessageStream({ messages }: MessageStreamProps) {
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
        </article>
      ))}
    </div>
  );
}
