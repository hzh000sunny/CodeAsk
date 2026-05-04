import { useMemo, useState } from "react";
import { AlertTriangle, FolderUp, X } from "lucide-react";

import type {
  WikiImportJobItemsRead,
  WikiImportJobRead,
  WikiImportPreflightRead,
} from "../../types/wiki";
import { Button } from "../ui/button";

export function WikiImportDialog({
  importItems,
  importJob,
  onApply,
  onClose,
  onFilesSelected,
  open,
  pending,
  preflight,
}: {
  importItems: WikiImportJobItemsRead | null;
  importJob: WikiImportJobRead | null;
  onApply: () => void;
  onClose: () => void;
  onFilesSelected: (files: File[]) => void;
  open: boolean;
  pending: boolean;
  preflight: WikiImportPreflightRead | null;
}) {
  const [fileLabel, setFileLabel] = useState("");

  const hasConflicts = useMemo(
    () => preflight != null && !preflight.ready,
    [preflight],
  );

  if (!open) {
    return null;
  }

  return (
    <div className="wiki-drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="wiki-drawer wide"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="wiki-drawer-header">
          <div>
            <h2>导入 Wiki</h2>
            <p>默认不显示任务状态栏，导入冲突在这里一次处理。</p>
          </div>
          <button className="list-menu-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>
        <div className="wiki-import-content">
          <label className="wiki-import-dropzone">
            <FolderUp size={20} />
            <strong>{fileLabel || "选择 Markdown 文件或目录"}</strong>
            <span>支持相对路径导入和资源引用校验</span>
            <input
              multiple
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                setFileLabel(files.length > 0 ? `已选择 ${files.length} 个文件` : "");
                if (files.length > 0) {
                  onFilesSelected(files);
                }
              }}
              type="file"
              {...{ webkitdirectory: "" }}
            />
          </label>

          {preflight ? (
            <section className="wiki-import-section">
              <div className="wiki-import-summary">
                <span>{preflight.summary.total_files} files</span>
                <span>{preflight.summary.conflict_count} conflicts</span>
                <span>{preflight.summary.warning_count} warnings</span>
              </div>
              <div className="wiki-import-items">
                {preflight.items.map((item) => (
                  <div className="wiki-import-item" key={item.relative_path}>
                    <div className="wiki-import-item-top">
                      <strong>{item.relative_path}</strong>
                      <span data-status={item.status}>{item.status}</span>
                    </div>
                    <div className="item-meta">{item.target_path}</div>
                    {item.issues.length > 0 ? (
                      <ul className="wiki-import-issues">
                        {item.issues.map((issue) => (
                          <li key={`${item.relative_path}-${issue.code}-${issue.target ?? "none"}`}>
                            <AlertTriangle size={12} />
                            <span>{issue.message}</span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {importJob ? (
            <section className="wiki-import-section">
              <div className="wiki-import-summary">
                <span>job_{importJob.id}</span>
                <span>{importJob.status}</span>
              </div>
              {importItems ? (
                <div className="wiki-import-items">
                  {importItems.items.map((item) => (
                    <div className="wiki-import-item" key={item.id}>
                      <div className="wiki-import-item-top">
                        <strong>{item.source_path}</strong>
                        <span data-status={item.status}>{item.status}</span>
                      </div>
                      <div className="item-meta">{item.target_path}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
        <div className="dialog-actions wiki-import-actions">
          <Button onClick={onClose} type="button" variant="secondary">
            关闭
          </Button>
          <Button
            disabled={pending || !preflight || hasConflicts}
            onClick={onApply}
            type="button"
            variant="primary"
          >
            导入并应用
          </Button>
        </div>
      </aside>
    </div>
  );
}
