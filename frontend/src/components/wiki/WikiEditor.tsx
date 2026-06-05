import { useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { ChevronRight, Clock3 } from "lucide-react";
import type { EditorView } from "@codemirror/view";

import { Button } from "../ui/button";
import { WikiLivePreview } from "./WikiLivePreview";
import { WikiSourceEditor } from "./WikiSourceEditor";

const MIN_RATIO = 0.25;
const MAX_RATIO = 0.75;
const KEY_STEP = 0.04;

export function WikiEditor({
  autosaveLabel,
  bodyMarkdown,
  breadcrumbSegments,
  isDirty,
  onCancel,
  onOpenHistory,
  onPublish,
  onToggleTree,
  publishing,
  showTreeToggle,
  title,
  imageSrcMap,
  linkHrefMap,
  setBodyMarkdown,
}: {
  autosaveLabel: string;
  bodyMarkdown: string;
  breadcrumbSegments: string[];
  isDirty: boolean;
  onCancel: () => void;
  onOpenHistory: () => void;
  onPublish: () => void;
  onToggleTree: () => void;
  publishing: boolean;
  showTreeToggle: boolean;
  title: string;
  imageSrcMap?: Record<string, string>;
  linkHrefMap?: Record<string, string>;
  setBodyMarkdown: (value: string) => void;
}) {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const sourceViewRef = useRef<EditorView | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const syncingRef = useRef(false);
  const [ratio, setRatio] = useState(0.5);

  // 报头面包屑：没有路径时退回标题，保证编辑态也始终点名「在改哪一篇」。
  const crumbs = breadcrumbSegments.length > 0 ? breadcrumbSegments : [title];
  const statusState = publishing ? "saving" : isDirty ? "dirty" : "clean";

  // 滚动同步：拖动任一栏，另一栏按滚动比例跟随；用一帧的锁避免来回触发。
  function syncScroll(from: "source" | "preview") {
    if (syncingRef.current) {
      return;
    }
    const sourceScroller = sourceViewRef.current?.scrollDOM ?? null;
    const previewScroller = previewRef.current;
    const src = from === "source" ? sourceScroller : previewScroller;
    const dst = from === "source" ? previewScroller : sourceScroller;
    if (!src || !dst) {
      return;
    }
    const srcMax = src.scrollHeight - src.clientHeight;
    const dstMax = dst.scrollHeight - dst.clientHeight;
    if (srcMax <= 0 || dstMax <= 0) {
      return;
    }
    syncingRef.current = true;
    dst.scrollTop = (src.scrollTop / srcMax) * dstMax;
    window.requestAnimationFrame(() => {
      syncingRef.current = false;
    });
  }

  function startDrag(event: React.PointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const grid = gridRef.current;
    if (!grid) {
      return;
    }
    const rect = grid.getBoundingClientRect();
    const onMove = (move: PointerEvent) => {
      const next = (move.clientX - rect.left) / rect.width;
      setRatio(Math.min(MAX_RATIO, Math.max(MIN_RATIO, next)));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.cursor = "";
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    document.body.style.cursor = "col-resize";
  }

  function onDividerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setRatio((value) => Math.max(MIN_RATIO, value - KEY_STEP));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setRatio((value) => Math.min(MAX_RATIO, value + KEY_STEP));
    } else if (event.key === "Home") {
      event.preventDefault();
      setRatio(0.5);
    }
  }

  const gridStyle = {
    "--col-a": `${ratio}fr`,
    "--col-b": `${1 - ratio}fr`,
  } as CSSProperties;

  return (
    <section className="wiki-editor-shell">
      {showTreeToggle ? (
        <button
          aria-label="展开目录"
          className="edge-collapse-button wiki-inline-toggle"
          data-collapsed="true"
          onClick={onToggleTree}
          type="button"
        >
          <ChevronRight size={15} />
        </button>
      ) : null}
      <header className="wiki-editor-masthead">
        <div className="wiki-editor-masthead-lead">
          <nav aria-label="文档路径" className="wiki-doc-breadcrumb">
            {crumbs.map((segment, index) => (
              <span
                className="wiki-doc-crumb"
                data-current={index === crumbs.length - 1 || undefined}
                key={`${segment}-${index}`}
              >
                {index > 0 ? (
                  <ChevronRight
                    aria-hidden="true"
                    className="wiki-doc-crumb-sep"
                    size={13}
                  />
                ) : null}
                <span>{segment}</span>
              </span>
            ))}
          </nav>
          <span
            aria-live="polite"
            className="wiki-editor-status"
            data-state={statusState}
          >
            <span aria-hidden="true" className="wiki-editor-status-dot" />
            {autosaveLabel}
          </span>
        </div>
        <div className="header-actions">
          <Button
            icon={<Clock3 size={15} />}
            onClick={onOpenHistory}
            type="button"
            variant="secondary"
          >
            历史版本
          </Button>
          <Button onClick={onCancel} type="button" variant="secondary">
            取消
          </Button>
          <Button
            disabled={publishing}
            onClick={onPublish}
            type="button"
            variant="primary"
          >
            {publishing ? "保存中…" : "保存"}
          </Button>
        </div>
      </header>
      <div className="wiki-editor-grid" ref={gridRef} style={gridStyle}>
        <WikiSourceEditor
          editorViewRef={sourceViewRef}
          onChange={setBodyMarkdown}
          onScroll={() => syncScroll("source")}
          value={bodyMarkdown}
        />
        <button
          aria-label="拖动调整源码与预览的宽度比例"
          aria-orientation="vertical"
          className="wiki-split-divider"
          onKeyDown={onDividerKeyDown}
          onPointerDown={startDrag}
          role="separator"
          tabIndex={0}
          type="button"
        />
        <WikiLivePreview
          content={bodyMarkdown}
          imageSrcMap={imageSrcMap}
          linkHrefMap={linkHrefMap}
          onScroll={() => syncScroll("preview")}
          scrollRef={previewRef}
        />
      </div>
    </section>
  );
}
