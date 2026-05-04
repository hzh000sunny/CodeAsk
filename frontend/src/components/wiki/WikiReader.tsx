import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session/session-clipboard";

export function WikiReader({
  content,
  imageSrcMap,
  linkHrefMap,
}: {
  content: string;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
}) {
  return (
    <article className="wiki-reader">
      <div className="wiki-reader-scroll">
        <div className="wiki-reader-body">
          <MarkdownRenderer
            content={content}
            imageSrcMap={imageSrcMap}
            linkHrefMap={linkHrefMap}
            onCopyCode={(code) => copyTextToClipboard(code)}
          />
        </div>
      </div>
    </article>
  );
}
