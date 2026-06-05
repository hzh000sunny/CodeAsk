import type { Ref, UIEvent } from "react";

import { Textarea } from "../ui/textarea";

export function WikiSourceEditor({
  onChange,
  onScroll,
  textareaRef,
  value,
}: {
  onChange: (value: string) => void;
  onScroll?: (event: UIEvent<HTMLTextAreaElement>) => void;
  textareaRef?: Ref<HTMLTextAreaElement>;
  value: string;
}) {
  const chars = value.length;
  const lines = value.length === 0 ? 0 : value.split("\n").length;
  return (
    <section className="wiki-editor-pane wiki-source-pane">
      <div className="wiki-pane-heading">
        <span className="wiki-pane-heading-label">Markdown 源码</span>
        <span className="wiki-pane-heading-meta">
          {chars} 字 · {lines} 行
        </span>
      </div>
      <Textarea
        className="wiki-source-editor"
        onChange={(event) => onChange(event.target.value)}
        onScroll={onScroll}
        placeholder="在此用 Markdown 撰写文档…"
        ref={textareaRef}
        spellCheck={false}
        value={value}
      />
    </section>
  );
}
