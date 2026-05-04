import { useMemo, useState } from "react";
import { X } from "lucide-react";

import type { WikiDocumentDiffRead, WikiDocumentVersionRead } from "../../types/wiki";
import { Button } from "../ui/button";

export function WikiVersionDrawer({
  currentVersionId,
  diff,
  loading,
  onClose,
  onCompare,
  onRollback,
  open,
  versions,
}: {
  currentVersionId: number | null;
  diff: WikiDocumentDiffRead | null;
  loading: boolean;
  onClose: () => void;
  onCompare: (fromVersionId: number, toVersionId: number) => void;
  onRollback: (versionId: number) => void;
  open: boolean;
  versions: WikiDocumentVersionRead[];
}) {
  const [compareFrom, setCompareFrom] = useState<number | null>(null);

  const compareTarget = useMemo(
    () => currentVersionId ?? versions[0]?.id ?? null,
    [currentVersionId, versions],
  );

  if (!open) {
    return null;
  }

  return (
    <div className="wiki-drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="wiki-drawer"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="wiki-drawer-header">
          <div>
            <h2>历史版本</h2>
            <p>只展示正式发布快照，不包含自动草稿。</p>
          </div>
          <button className="list-menu-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>
        <div className="wiki-version-scroll">
          <div className="wiki-version-list">
            {versions.map((version) => (
              <div className="wiki-version-card" key={version.id}>
                <div className="wiki-version-card-top">
                  <strong>v{version.version_no}</strong>
                  <span>{version.id === currentVersionId ? "当前" : "历史"}</span>
                </div>
                <div className="item-meta">
                  {new Date(version.created_at).toLocaleString()} · {version.created_by_subject_id}
                </div>
                <div className="wiki-version-actions">
                  {version.id !== compareTarget ? (
                    <Button
                      onClick={() => {
                        setCompareFrom(version.id);
                        if (compareTarget != null) {
                          onCompare(version.id, compareTarget);
                        }
                      }}
                      type="button"
                      variant="quiet"
                    >
                      对比当前
                    </Button>
                  ) : null}
                  {version.id !== currentVersionId ? (
                    <Button
                      onClick={() => onRollback(version.id)}
                      type="button"
                      variant="quiet"
                    >
                      回滚
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <div className="wiki-diff-panel">
            <strong>{compareFrom && diff ? `v${diff.from_version_no} -> v${diff.to_version_no}` : "选择版本后查看 diff"}</strong>
            <pre>{loading ? "正在加载 diff..." : diff?.patch || "暂无 diff"}</pre>
          </div>
        </div>
      </aside>
    </div>
  );
}
