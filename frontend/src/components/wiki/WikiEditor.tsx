import { ChevronRight, Clock3 } from "lucide-react";

import { Button } from "../ui/button";
import { WikiLivePreview } from "./WikiLivePreview";
import { WikiSourceEditor } from "./WikiSourceEditor";

export function WikiEditor({
  autosaveLabel,
  bodyMarkdown,
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
      <div className="page-header compact wiki-page-header">
        <div>
          <h1>{title}</h1>
          <p>{autosaveLabel}</p>
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
          <Button disabled={publishing} onClick={onPublish} type="button" variant="primary">
            保存
          </Button>
        </div>
      </div>
      <div className="wiki-editor-grid">
        <WikiSourceEditor onChange={setBodyMarkdown} value={bodyMarkdown} />
        <WikiLivePreview
          content={bodyMarkdown}
          imageSrcMap={imageSrcMap}
          linkHrefMap={linkHrefMap}
        />
      </div>
    </section>
  );
}
