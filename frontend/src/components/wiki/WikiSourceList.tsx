import { PencilLine, RotateCw } from "lucide-react";

import type { WikiSourceRead } from "../../types/wiki";
import { Button } from "../ui/button";
import { WikiSourceSyncResult } from "./WikiSourceSyncResult";

function metadataSummary(source: WikiSourceRead) {
  const metadata = source.metadata_json;
  if (metadata && typeof metadata === "object" && !Array.isArray(metadata)) {
    const rootPath = metadata.root_path;
    if (typeof rootPath === "string" && rootPath.trim()) {
      return rootPath;
    }
  }
  return source.uri ?? "未配置 URI";
}

export function WikiSourceList({
  onEdit,
  onSync,
  recentSyncedSourceId,
  syncPendingSourceId,
  sources,
}: {
  onEdit: (source: WikiSourceRead) => void;
  onSync: (source: WikiSourceRead) => void;
  recentSyncedSourceId: number | null;
  syncPendingSourceId: number | null;
  sources: WikiSourceRead[];
}) {
  if (sources.length === 0) {
    return (
      <div className="wiki-source-empty">
        <strong>还没有登记来源</strong>
        <p>把导入目录、人工整理材料或会话沉淀来源登记在这里，后续同步和追溯会更清晰。</p>
      </div>
    );
  }

  return (
    <div className="wiki-source-list">
      {sources.map((source) => {
        const syncing = syncPendingSourceId === source.id;
        return (
          <article
            className="wiki-source-row"
            data-testid={`wiki-source-row-${source.id}`}
            key={source.id}
          >
            <div className="wiki-source-row-main">
              <div className="wiki-source-row-top">
                <strong>{source.display_name}</strong>
              </div>
              <p>{metadataSummary(source)}</p>
              <WikiSourceSyncResult
                highlightRecent={recentSyncedSourceId === source.id}
                source={source}
              />
            </div>
            <div className="wiki-source-row-actions">
              <Button
                aria-label="编辑来源"
                icon={<PencilLine size={15} />}
                onClick={() => onEdit(source)}
                type="button"
                variant="secondary"
              >
                编辑
              </Button>
              <Button
                aria-label="同步来源"
                icon={<RotateCw size={15} />}
                onClick={() => onSync(source)}
                type="button"
                variant="secondary"
              >
                {syncing ? "同步中" : "同步"}
              </Button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
