import { useEffect, useRef, useState, type ReactNode } from "react";

import { MarkdownRenderer, buildMarkdownHeadingId } from "../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session/session-clipboard";
import { WikiTableOfContents, type WikiTocHeading } from "./WikiTableOfContents";

// 大纲只收 h1–h3：再深的层级会把侧栏目录撑得又长又碎，对导航帮助有限。
const TOC_MAX_LEVEL = 3;

export function WikiReader({
  brokenImageTargets,
  content,
  header,
  headingTarget,
  imageSrcMap,
  linkHrefMap,
}: {
  brokenImageTargets?: Iterable<string>;
  content: string;
  header?: ReactNode;
  headingTarget?: string | null;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const [headings, setHeadings] = useState<WikiTocHeading[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // 正文渲染完后，直接从 DOM 里采集标题（react-markdown 已生成与正文一致的 id），
  // 不另行解析 markdown，省得在围栏代码/转义等边角和正文锚点对不上。
  useEffect(() => {
    const root = bodyRef.current;
    if (!root) {
      setHeadings([]);
      return;
    }
    const collected = Array.from(
      root.querySelectorAll<HTMLElement>("h1[id], h2[id], h3[id]"),
    ).map((node) => ({
      id: node.id,
      text: (node.dataset.headingText ?? node.textContent ?? "").trim(),
      level: Number(node.tagName.slice(1)),
    }));
    setHeadings(collected.filter((heading) => heading.text.length > 0));
  }, [content]);

  // 深链定位到指定标题。
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

  // 滚动联动（scrollspy）：高亮当前已滚过的最后一个标题。
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller || headings.length === 0) {
      setActiveId(null);
      return;
    }
    let frame = 0;
    const compute = () => {
      frame = 0;
      const threshold = scroller.getBoundingClientRect().top + 24;
      let current = headings[0].id;
      for (const heading of headings) {
        const element = document.getElementById(heading.id);
        if (!element) {
          continue;
        }
        if (element.getBoundingClientRect().top - threshold <= 1) {
          current = heading.id;
        } else {
          break;
        }
      }
      setActiveId(current);
    };
    const onScroll = () => {
      if (!frame) {
        frame = window.requestAnimationFrame(compute);
      }
    };
    compute();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      if (frame) {
        window.cancelAnimationFrame(frame);
      }
    };
  }, [headings]);

  const minLevel = headings.reduce(
    (lowest, heading) => Math.min(lowest, heading.level),
    TOC_MAX_LEVEL,
  );
  const hasToc = headings.length > 1;

  function scrollToHeading(id: string) {
    const element = document.getElementById(id);
    if (!element) {
      return;
    }
    const prefersReduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    element.scrollIntoView({
      block: "start",
      behavior: prefersReduced ? "auto" : "smooth",
    });
    setActiveId(id);
  }

  return (
    <article className="wiki-reader">
      {header}
      <div className="wiki-reader-scroll" ref={scrollRef}>
        <div className="wiki-reader-canvas" data-has-toc={hasToc || undefined}>
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
          {hasToc ? (
            <WikiTableOfContents
              activeId={activeId}
              headings={headings}
              minLevel={minLevel}
              onSelect={scrollToHeading}
            />
          ) : null}
        </div>
      </div>
    </article>
  );
}
