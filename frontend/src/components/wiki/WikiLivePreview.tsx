import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session/session-clipboard";

export function WikiLivePreview({
  content,
  imageSrcMap,
  linkHrefMap,
}: {
  content: string;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
}) {
  return (
    <section className="wiki-editor-pane wiki-live-preview">
      <div className="wiki-pane-heading">实时预览</div>
      <div className="wiki-live-preview-body">
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
