import { X } from "lucide-react";

import type { WikiDocumentDetailRead } from "../../types/wiki";

export function WikiDetailDrawer({
  document,
  path,
  onClose,
  open,
  updatedAt,
}: {
  document: WikiDocumentDetailRead | null;
  path: string | null;
  onClose: () => void;
  open: boolean;
  updatedAt: string | null;
}) {
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
              <h2>文档详情</h2>
              <p>辅助信息不常驻占用正文区域。</p>
            </div>
            <button className="list-menu-button" onClick={onClose} type="button">
              <X size={16} />
            </button>
          </div>
          {document ? (
            <dl className="wiki-detail-grid">
              <dt>标题</dt>
              <dd>{document.title}</dd>
              <dt>路径</dt>
              <dd>{path ?? "未知"}</dd>
              <dt>更新时间</dt>
              <dd>{updatedAt ? new Date(updatedAt).toLocaleString() : "未知"}</dd>
              <dt>索引状态</dt>
              <dd>{document.index_status}</dd>
              <dt>当前版本</dt>
              <dd>{document.current_version_id ?? "未发布"}</dd>
              <dt>来源</dt>
              <dd>{document.provenance_json?.source ? String(document.provenance_json.source) : "未知"}</dd>
              <dt>断链</dt>
              <dd>
                链接 {document.broken_refs_json.links.length} / 资源 {document.broken_refs_json.assets.length}
              </dd>
            </dl>
          ) : null}
        </aside>
      </div>
    );
}
