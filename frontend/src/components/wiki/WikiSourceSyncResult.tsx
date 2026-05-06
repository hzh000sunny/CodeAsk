import type { WikiSourceRead } from "../../types/wiki";

function formatStatus(status: WikiSourceRead["status"]) {
  if (status === "active") {
    return "正常";
  }
  if (status === "failed") {
    return "失败";
  }
  return "已归档";
}

function formatKind(kind: WikiSourceRead["kind"]) {
  if (kind === "directory_import") {
    return "目录导入";
  }
  if (kind === "session_promotion") {
    return "会话晋级";
  }
  return "手动录入";
}

function formatLastSynced(lastSyncedAt: string | null, highlightRecent: boolean) {
  if (highlightRecent) {
    return "刚刚同步";
  }
  if (!lastSyncedAt) {
    return "尚未同步";
  }
  const date = new Date(lastSyncedAt);
  if (Number.isNaN(date.getTime())) {
    return "已同步";
  }
  return `同步于 ${date.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

export function WikiSourceSyncResult({
  highlightRecent = false,
  source,
}: {
  highlightRecent?: boolean;
  source: WikiSourceRead;
}) {
  return (
    <div className="wiki-source-sync-result">
      <span className="wiki-source-pill">{formatKind(source.kind)}</span>
      <span className="wiki-source-pill">{formatStatus(source.status)}</span>
      <span className="wiki-source-sync-copy">
        {formatLastSynced(source.last_synced_at, highlightRecent)}
      </span>
    </div>
  );
}
