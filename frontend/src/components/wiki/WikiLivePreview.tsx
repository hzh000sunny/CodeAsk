import type { Ref, UIEvent } from "react";

import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session/session-clipboard";

export function WikiLivePreview({
  content,
  imageSrcMap,
  linkHrefMap,
  onScroll,
  scrollRef,
}: {
  content: string;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
  onScroll?: (event: UIEvent<HTMLDivElement>) => void;
  scrollRef?: Ref<HTMLDivElement>;
}) {
  return (
    <section className="wiki-editor-pane wiki-live-preview">
      <div className="wiki-pane-heading">
        <span className="wiki-pane-heading-label">实时预览</span>
        <span className="wiki-pane-heading-meta">跟随源码渲染</span>
      </div>
      <div
        className="wiki-live-preview-body"
        onScroll={onScroll}
        ref={scrollRef}
      >
        <MarkdownRenderer
          content={content}
          imageSrcMap={imageSrcMap}
          linkHrefMap={linkHrefMap}
          onCopyCode={(code) => copyTextToClipboard(code)}
        />
      </div>
    </section>
  );
}
