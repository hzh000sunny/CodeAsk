import { X } from "lucide-react";

import type { WikiDocumentDetailRead } from "../../types/wiki";

function readSummaryValue(
  summary: Record<string, unknown> | null | undefined,
  key: string,
): string | null {
  const value = summary?.[key];
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return null;
}

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
  const summary = document?.provenance_summary;
  const sourceLabel =
    readSummaryValue(summary, "source_label") ??
    (document?.provenance_json?.source ? String(document.provenance_json.source) : "未知");
  const sourceDisplayName = readSummaryValue(summary, "source_display_name");
  const sourcePath = readSummaryValue(summary, "source_path");
  const sourceUri = readSummaryValue(summary, "source_uri");
  const importSessionId = readSummaryValue(summary, "import_session_id");
  const importJobId = readSummaryValue(summary, "import_job_id");
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
            <dt>来源类型</dt>
            <dd>{sourceLabel}</dd>
            {sourceDisplayName ? (
              <>
                <dt>来源名称</dt>
                <dd>{sourceDisplayName}</dd>
              </>
            ) : null}
            {sourcePath ? (
              <>
                <dt>源相对路径</dt>
                <dd>{sourcePath}</dd>
              </>
            ) : null}
            {sourceUri ? (
              <>
                <dt>来源 URI</dt>
                <dd>{sourceUri}</dd>
              </>
            ) : null}
            {importSessionId ? (
              <>
                <dt>导入会话</dt>
                <dd>{importSessionId}</dd>
              </>
            ) : null}
            {importJobId ? (
              <>
                <dt>导入任务</dt>
                <dd>{importJobId}</dd>
              </>
            ) : null}
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
