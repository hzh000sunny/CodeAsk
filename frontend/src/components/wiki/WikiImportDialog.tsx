import { useEffect, useMemo, useState } from "react";
import { FileText, FolderTree, FolderUp, X } from "lucide-react";

import type {
  WikiImportSelectionItem,
  WikiImportSessionItemsRead,
  WikiImportSessionRead,
} from "../../types/wiki";
import { filterWikiImportFiles } from "../../lib/wiki/import-files";
import { formatWikiPathMentions, formatWikiStoredPath } from "../../lib/wiki/tree";
import { Button } from "../ui/button";

type QueueFilter =
  | "all"
  | "active"
  | "pending"
  | "uploading"
  | "uploaded"
  | "conflict"
  | "failed"
  | "ignored"
  | "skipped";

export function WikiImportDialog({
  errorMessage,
  hasUnfinishedSession,
  importTargetLabel,
  actionPendingKey,
  onBulkResolve,
  onCancelImport,
  onClose,
  onContinueInBackground,
  onFilesSelected,
  onResolveItem,
  onRetryFailed,
  onRetryItem,
  open,
  pending,
  session,
  sessionItems,
}: {
  actionPendingKey: string | null;
  errorMessage: string;
  hasUnfinishedSession: boolean;
  importTargetLabel: string | null;
  onBulkResolve: (action: "skip_all" | "overwrite_all") => void;
  onCancelImport: () => void;
  onClose: () => void;
  onContinueInBackground: () => void;
  onFilesSelected: (payload: {
    files: File[];
    items: WikiImportSelectionItem[];
    mode: "markdown" | "directory";
  }) => void;
  onResolveItem: (itemId: number, action: "skip" | "overwrite") => void;
  onRetryFailed: () => void;
  onRetryItem: (itemId: number) => void;
  open: boolean;
  pending: boolean;
  session: WikiImportSessionRead | null;
  sessionItems: WikiImportSessionItemsRead | null;
}) {
  const [fileLabel, setFileLabel] = useState("");
  const [selectionMessage, setSelectionMessage] = useState("");
  const [selectionTone, setSelectionTone] = useState<"info" | "warning" | "danger">("info");
  const [selectionIgnoredItems, setSelectionIgnoredItems] = useState<
    Array<{ source_path: string; ignore_reason: string | null }>
  >([]);
  const [ignoredExpanded, setIgnoredExpanded] = useState(false);
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");

  const queueItems = sessionItems?.items ?? [];
  const activeQueueItems = useMemo(
    () => queueItems.filter((item) => item.status !== "ignored"),
    [queueItems],
  );
  const ignoredQueueItems = useMemo(
    () => queueItems.filter((item) => item.status === "ignored"),
    [queueItems],
  );
  const ignoredItems = useMemo(() => {
    if (ignoredQueueItems.length > 0) {
      return ignoredQueueItems.map((item) => ({
        source_path: item.source_path,
        ignore_reason: item.ignore_reason,
        status: item.status,
      }));
    }
    return selectionIgnoredItems.map((item) => ({
      ...item,
      status: "ignored",
    }));
  }, [ignoredQueueItems, selectionIgnoredItems]);
  const summaryProgressPercent = useMemo(() => {
    if (activeQueueItems.length === 0) {
      return 0;
    }
    const totalProgress = activeQueueItems.reduce((sum, item) => {
      switch (item.status) {
        case "uploaded":
        case "skipped":
        case "conflict":
        case "failed":
          return sum + 100;
        case "uploading":
          return sum + item.progress_percent;
        case "pending":
        default:
          return sum;
      }
    }, 0);
    return Math.round(totalProgress / activeQueueItems.length);
  }, [activeQueueItems]);
  const currentProcessingLabel = useMemo(() => {
    const uploadingItem = activeQueueItems.find((item) => item.status === "uploading");
    if (uploadingItem) {
      return uploadingItem.source_path;
    }
    const pendingItem = activeQueueItems.find((item) => item.status === "pending");
    return pendingItem?.source_path ?? null;
  }, [activeQueueItems]);

  useEffect(() => {
    if (!open) {
      setFileLabel("");
      setSelectionMessage("");
      setSelectionTone("info");
      setSelectionIgnoredItems([]);
      setIgnoredExpanded(false);
      setCloseConfirmOpen(false);
      setQueueFilter("all");
    }
  }, [open]);

  const visibleQueueItems = useMemo(() => {
    if (queueFilter === "ignored") {
      return [];
    }
    if (queueFilter === "all") {
      return activeQueueItems;
    }
    if (queueFilter === "active") {
      return activeQueueItems.filter(
        (item) =>
          item.status === "pending" ||
          item.status === "uploading" ||
          item.status === "failed" ||
          item.status === "conflict",
      );
    }
    return activeQueueItems.filter((item) => item.status === queueFilter);
  }, [activeQueueItems, queueFilter]);

  const showingIgnoredItems = session ? queueFilter === "ignored" : ignoredExpanded;
  const queueHeadline = session
    ? `已选择 ${session.summary.total_files} 个文件`
    : fileLabel
      ? "已选择文件，队列会继续展示上传进度和冲突处理。"
      : "选择文件后，这里会显示完整队列、上传进度和冲突处理。";

  function toggleSummaryFilter(filter: QueueFilter) {
    setQueueFilter((current) => (current === filter ? "all" : filter));
  }

  function renderSummaryFilterButton(label: string, count: number, filter: QueueFilter) {
    return (
      <button
        aria-pressed={queueFilter === filter}
        className="wiki-import-summary-button"
        onClick={() => toggleSummaryFilter(filter)}
        type="button"
      >
        {label} {count}
      </button>
    );
  }

  function requestClose() {
    if (hasUnfinishedSession) {
      setCloseConfirmOpen(true);
      return;
    }
    onClose();
  }

  async function handleFilesPicked(files: File[], mode: "markdown" | "directory") {
    if (files.length === 0) {
      setFileLabel("");
      setSelectionMessage("");
      setSelectionTone("info");
      setSelectionIgnoredItems([]);
      return;
    }

    const result = await filterWikiImportFiles(files, mode);
    setSelectionIgnoredItems(
      result.items
        .filter((item) => !item.included)
        .map((item) => ({
          source_path: item.relativePath,
          ignore_reason: item.ignoreReason,
        })),
    );

    if (result.accepted.length === 0) {
      setFileLabel("");
      setSelectionTone("danger");
      setSelectionMessage(
        mode === "directory"
          ? "当前目录里没有可导入的 Markdown 或支持的静态资源文件。"
          : "只支持导入 Markdown 文件。",
      );
      return;
    }

    if (mode === "directory") {
      const firstRelativePath = result.items.find((item) => item.included)?.relativePath ?? "";
      const directoryName = firstRelativePath.split("/")[0] || "目录";
      setFileLabel(`已选择目录 ${directoryName}（${result.accepted.length} 个可导入文件）`);
    } else if (result.accepted.length === 1) {
      setFileLabel(`已选择 Markdown：${result.accepted[0].name}`);
    } else {
      setFileLabel(`已选择 ${result.accepted.length} 个 Markdown 文件`);
    }

    if (result.skippedCount > 0) {
      setSelectionTone("warning");
      setSelectionMessage(
        `已忽略 ${result.skippedCount} 个非 Wiki 文件，仅保留 Markdown 和被 Markdown 引用的静态资源。`,
      );
    } else {
      setSelectionMessage("");
      setSelectionTone("info");
    }

    onFilesSelected({
      files: result.accepted,
      items: result.items,
      mode,
    });
  }

  if (!open) {
    return null;
  }

  return (
    <div className="wiki-drawer-backdrop" onClick={requestClose} role="presentation">
      <aside
        aria-labelledby="wiki-import-title"
        className="wiki-drawer wide"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="wiki-drawer-header">
          <div>
            <h2 id="wiki-import-title">导入 Wiki</h2>
            <p>
              {importTargetLabel
                ? `将内容导入到 ${importTargetLabel}`
                : "导入队列会直接展示完整文件列表。"}
            </p>
          </div>
          <button
            aria-label="关闭导入抽屉"
            className="list-menu-button"
            onClick={requestClose}
            type="button"
          >
            <X size={16} />
          </button>
        </div>
        <div className="wiki-import-content">
          <section className="wiki-import-picker-grid wiki-import-picker-grid-compact">
            <label className="wiki-import-dropzone" data-mode="markdown">
              <span className="wiki-import-dropzone-icon" aria-hidden="true">
                <FileText size={18} />
              </span>
              <strong>导入 Markdown</strong>
              <span>适合零散补录。直接选择一个或多个 Markdown 文件，落到当前目录。</span>
              <span className="file-button wiki-import-picker-button">
                选择 Markdown
                <input
                  accept=".md,.markdown,text/markdown"
                  aria-label="选择 Markdown 文件"
                  multiple
                  onChange={(event) => {
                    const files = Array.from(event.target.files ?? []);
                    void handleFilesPicked(files, "markdown");
                    event.currentTarget.value = "";
                  }}
                  type="file"
                />
              </span>
            </label>
            <label className="wiki-import-dropzone" data-mode="directory">
              <span className="wiki-import-dropzone-icon" aria-hidden="true">
                <FolderTree size={18} />
              </span>
              <strong>导入目录</strong>
              <span>适合完整迁移。保留目录层级、相对图片路径和内部链接关系。</span>
              <span className="file-button wiki-import-picker-button">
                选择目录
                <input
                  aria-label="选择 Wiki 目录"
                  multiple
                  onChange={(event) => {
                    const files = Array.from(event.target.files ?? []);
                    void handleFilesPicked(files, "directory");
                    event.currentTarget.value = "";
                  }}
                  type="file"
                  {...{ webkitdirectory: "" }}
                />
              </span>
            </label>
          </section>

          <section className="wiki-import-section" data-empty={!session && ignoredItems.length === 0}>
            <div className="wiki-import-section-head">
              <div>
                <h3>导入队列</h3>
                <p>{queueHeadline}</p>
              </div>
              {importTargetLabel ? (
                <div className="wiki-import-section-target">目标目录 {importTargetLabel}</div>
              ) : null}
            </div>

            {fileLabel ? <div className="wiki-import-selection-summary">{fileLabel}</div> : null}

            {selectionMessage ? (
              <div className="wiki-import-status-banner" data-tone={selectionTone} role="status">
                {selectionMessage}
              </div>
            ) : null}

            {pending && fileLabel ? (
              <div className="wiki-import-status-banner" data-tone="info" role="status">
                正在准备导入队列…
              </div>
            ) : null}

            {errorMessage ? (
              <div className="wiki-import-status-banner" data-tone="danger" role="alert">
                {formatWikiPathMentions(errorMessage)}
              </div>
            ) : null}

            {session ? (
              <>
                <div className="wiki-import-summary">
                  {renderSummaryFilterButton("待上传", session.summary.pending_count, "pending")}
                  {renderSummaryFilterButton("上传中", session.summary.uploading_count, "uploading")}
                  {renderSummaryFilterButton("已上传", session.summary.uploaded_count, "uploaded")}
                  {renderSummaryFilterButton("冲突", session.summary.conflict_count, "conflict")}
                  {renderSummaryFilterButton("失败", session.summary.failed_count, "failed")}
                  {renderSummaryFilterButton("已忽略", session.summary.ignored_count, "ignored")}
                  {renderSummaryFilterButton("已跳过", session.summary.skipped_count, "skipped")}
                </div>
                {session.summary.failed_count > 0 ? (
                  <div className="wiki-import-summary-actions">
                    <Button
                      disabled={actionPendingKey != null}
                      onClick={() => onRetryFailed()}
                      type="button"
                      variant="quiet"
                    >
                      {actionPendingKey === "session:retry-failed" ? "处理中…" : "重试失败项"}
                    </Button>
                  </div>
                ) : null}
                {activeQueueItems.length > 0 ? (
                  <div aria-label="导入队列筛选" className="report-filter-tabs" role="tablist">
                    <button
                      aria-selected={queueFilter === "all"}
                      className="report-filter-button"
                      onClick={() => setQueueFilter("all")}
                      role="tab"
                      type="button"
                    >
                      <span>全部</span>
                      <small>{activeQueueItems.length}</small>
                    </button>
                    <button
                      aria-selected={queueFilter === "active"}
                      className="report-filter-button"
                      onClick={() => setQueueFilter("active")}
                      role="tab"
                      type="button"
                    >
                      <span>仅看进行中与失败</span>
                      <small>
                        {
                          activeQueueItems.filter(
                            (item) =>
                              item.status === "pending" ||
                              item.status === "uploading" ||
                              item.status === "failed" ||
                              item.status === "conflict",
                          ).length
                        }
                      </small>
                    </button>
                  </div>
                ) : null}
                {activeQueueItems.length > 0 ? (
                  <div className="wiki-import-summary-meta">
                    <div className="wiki-import-summary-meta-card">
                      <span>总进度 {summaryProgressPercent}%</span>
                      {currentProcessingLabel ? (
                        <strong>当前处理 {currentProcessingLabel}</strong>
                      ) : (
                        <strong>队列已处理完成</strong>
                      )}
                    </div>
                  </div>
                ) : null}

                {showingIgnoredItems && ignoredItems.length > 0 ? (
                  <section className="wiki-import-ignored">
                    <div className="wiki-import-items">
                      {ignoredItems.map((item) => (
                        <article className="wiki-import-item" key={item.source_path}>
                          <div className="wiki-import-item-top">
                            <div>
                              <strong>{item.source_path}</strong>
                              <div className="item-meta">{item.ignore_reason ?? "ignored"}</div>
                            </div>
                            <span data-status={item.status}>{statusLabel(item.status)}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}

                {visibleQueueItems.length > 0 ? (
                  <div className="wiki-import-items">
                    {visibleQueueItems.map((item) => (
                      <article className="wiki-import-item" key={item.id}>
                        <div className="wiki-import-item-top">
                          <div>
                            <strong>{item.source_path}</strong>
                            <div className="item-meta">
                              {formatWikiStoredPath(item.target_path) ?? "未分配目标路径"}
                            </div>
                          </div>
                          <span data-status={item.status}>{statusLabel(item.status)}</span>
                        </div>
                        <div className="wiki-import-progress">
                          <div
                            className="wiki-import-progress-bar"
                            style={{ width: `${item.progress_percent}%` }}
                          />
                        </div>
                        {item.error_message ? (
                          <div className="item-meta" role="note">
                            {formatWikiPathMentions(item.error_message)}
                          </div>
                        ) : null}
                        {item.status === "conflict" ? (
                          <div className="wiki-import-conflict-actions">
                            <Button
                              disabled={actionPendingKey != null}
                              onClick={() => onResolveItem(item.id, "overwrite")}
                              type="button"
                              variant="primary"
                            >
                              {actionPendingKey === `item:${item.id}:overwrite` ? "处理中…" : "覆盖"}
                            </Button>
                            <Button
                              disabled={actionPendingKey != null}
                              onClick={() => onResolveItem(item.id, "skip")}
                              type="button"
                              variant="secondary"
                            >
                              {actionPendingKey === `item:${item.id}:skip` ? "处理中…" : "跳过"}
                            </Button>
                            <Button
                              disabled={actionPendingKey != null}
                              onClick={() => onBulkResolve("overwrite_all")}
                              type="button"
                              variant="quiet"
                            >
                              {actionPendingKey === "bulk:overwrite_all" ? "处理中…" : "全部覆盖"}
                            </Button>
                            <Button
                              disabled={actionPendingKey != null}
                              onClick={() => onBulkResolve("skip_all")}
                              type="button"
                              variant="quiet"
                            >
                              {actionPendingKey === "bulk:skip_all" ? "处理中…" : "全部跳过"}
                            </Button>
                          </div>
                        ) : null}
                        {item.status === "failed" ? (
                          <div className="wiki-import-conflict-actions">
                            <Button
                              disabled={actionPendingKey != null}
                              onClick={() => onRetryItem(item.id)}
                              type="button"
                              variant="primary"
                            >
                              {actionPendingKey === `item:${item.id}:retry` ? "处理中…" : "重试"}
                            </Button>
                          </div>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="wiki-import-empty-queue">
                <div className="wiki-import-empty-queue-icon">
                  <FolderUp aria-hidden="true" size={18} />
                </div>
                <div>
                  <strong>选择文件后开始建立导入队列</strong>
                  <p>这里会显示可上传文件、忽略项、冲突处理和逐个文件的进度。</p>
                </div>
              </div>
            )}

            {!session && ignoredItems.length > 0 ? (
              <section className="wiki-import-ignored">
                <button
                  className="wiki-import-ignored-toggle"
                  onClick={() => setIgnoredExpanded((value) => !value)}
                  type="button"
                >
                  已忽略 {ignoredItems.length} 个文件
                </button>
                {ignoredExpanded ? (
                  <div className="wiki-import-items">
                    {ignoredItems.map((item) => (
                      <article className="wiki-import-item" key={item.source_path}>
                        <div className="wiki-import-item-top">
                          <div>
                            <strong>{item.source_path}</strong>
                            <div className="item-meta">{item.ignore_reason ?? "ignored"}</div>
                          </div>
                          <span data-status={item.status}>{statusLabel(item.status)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : null}
              </section>
            ) : null}
          </section>
        </div>
        <div className="dialog-actions wiki-import-actions">
          <Button onClick={requestClose} type="button" variant="secondary">
            关闭
          </Button>
        </div>
        {closeConfirmOpen ? (
          <div
            className="dialog-backdrop"
            onClick={() => setCloseConfirmOpen(false)}
            role="presentation"
          >
            <section
              aria-labelledby="wiki-import-close-title"
              aria-modal="true"
              className="confirm-dialog wiki-node-dialog wiki-leave-dialog"
              onClick={(event) => event.stopPropagation()}
              role="dialog"
            >
              <div className="dialog-icon warning">
                <X aria-hidden="true" size={18} />
              </div>
              <div className="dialog-content">
                <h2 id="wiki-import-close-title">导入尚未完成</h2>
                <p>可以先关闭抽屉，让上传继续在后台进行，或者直接取消本次导入。</p>
                <div className="dialog-actions wiki-dialog-actions-stack">
                  <Button
                    onClick={() => setCloseConfirmOpen(false)}
                    type="button"
                    variant="secondary"
                  >
                    继续留在此处
                  </Button>
                  <Button
                    onClick={() => {
                      setCloseConfirmOpen(false);
                      onContinueInBackground();
                    }}
                    type="button"
                    variant="secondary"
                  >
                    继续后台
                  </Button>
                  <Button
                    onClick={() => {
                      setCloseConfirmOpen(false);
                      onCancelImport();
                    }}
                    type="button"
                    variant="danger"
                  >
                    取消上传
                  </Button>
                </div>
              </div>
            </section>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

function statusLabel(status: string) {
  switch (status) {
    case "pending":
      return "待上传";
    case "uploading":
      return "上传中";
    case "uploaded":
      return "已上传";
    case "conflict":
      return "冲突待处理";
    case "failed":
      return "失败";
    case "ignored":
      return "已忽略";
    case "skipped":
      return "已跳过";
    default:
      return status;
  }
}
