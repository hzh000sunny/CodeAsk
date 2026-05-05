import { useEffect, useRef } from "react";

import { MarkdownRenderer, buildMarkdownHeadingId } from "../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session/session-clipboard";

export function WikiReader({
  brokenImageTargets,
  content,
  headingTarget,
  imageSrcMap,
  linkHrefMap,
}: {
  brokenImageTargets?: Iterable<string>;
  content: string;
  headingTarget?: string | null;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
}) {
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!headingTarget) {
      return;
    }
    const nextId = buildMarkdownHeadingId(headingTarget, "wiki-heading");
    const heading =
      Array.from(bodyRef.current?.querySelectorAll<HTMLElement>("[id]") ?? []).find(
        (item) => item.id === nextId,
      ) ?? null;
    if (!heading) {
      return;
    }
    heading.scrollIntoView({ block: "start" });
  }, [content, headingTarget]);

  return (
    <article className="wiki-reader">
      <div className="wiki-reader-scroll">
        <div className="wiki-reader-body" ref={bodyRef}>
          <MarkdownRenderer
            brokenImageTargets={brokenImageTargets}
            content={content}
            headingIdPrefix="wiki-heading"
            imageSrcMap={imageSrcMap}
            linkHrefMap={linkHrefMap}
            onCopyCode={(code) => copyTextToClipboard(code)}
          />
        </div>
      </div>
    </article>
  );
}
