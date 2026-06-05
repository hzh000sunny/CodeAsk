import { ChevronRight } from "lucide-react";

import type { WikiDocumentDetailRead, WikiReportDetailRead } from "../../types/wiki";
import { copyTextToClipboard } from "../session/session-clipboard";
import { WikiEditor } from "./WikiEditor";
import { WikiEmptyState } from "./WikiEmptyState";
import { WikiFloatingActions } from "./WikiFloatingActions";
import { WikiReader } from "./WikiReader";
import { WikiReportViewer } from "./WikiReportViewer";

// 报头面包屑：从特性开始的绝对路径，含当前文档本身（标题已去掉，不再做末段裁剪）。
// 例：特性「OpenCode」下知识库里的 agent → OpenCode › 知识库 › agent。
function buildBreadcrumbSegments(featureName: string | null, path: string | null): string[] {
  const segments = (path ?? "")
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean);
  return featureName ? [featureName, ...segments] : segments;
}

function formatUpdatedAt(value: string | null): string | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function WikiWorkspacePane({
  activeFeature,
  brokenImageTargets,
  canCreate,
  canEdit,
  document,
  editingBody,
  headingTarget,
  imageSrcMap,
  linkHrefMap,
  onCreateDocument,
  onEdit,
  onOpenDetail,
  onOpenFeaturePage,
  onOpenHistory,
  onOpenImport,
  onOpenSources,
  onRequestCancelEdit,
  onSave,
  onToggleTree,
  publishPending,
  report,
  routeMode,
  saveToast,
  selectedNodePath,
  setSaveToast,
  setEditingBody,
  showTreeToggle,
  showNoFeatureState,
  autosaveLabel,
  activeFeatureName,
  activeFeatureIsHistory,
  featureHasDocuments,
  hasSelection,
  updatedAt,
}: {
  activeFeature: { id: number } | null;
  activeFeatureName: string | null;
  activeFeatureIsHistory: boolean;
  featureHasDocuments: boolean;
  hasSelection: boolean;
  brokenImageTargets: Set<string>;
  canCreate: boolean;
  canEdit: boolean;
  document: WikiDocumentDetailRead | null;
  editingBody: string;
  headingTarget: string | null;
  imageSrcMap: Record<string, string>;
  linkHrefMap: Record<string, string>;
  onCreateDocument: (() => void) | undefined;
  onEdit: () => void;
  onOpenDetail: () => void;
  onOpenFeaturePage: () => void;
  onOpenHistory: () => void;
  onOpenImport: () => void;
  onOpenSources: () => void;
  onRequestCancelEdit: () => void;
  onSave: () => void;
  onToggleTree: () => void;
  publishPending: boolean;
  report: WikiReportDetailRead | null;
  routeMode: "view" | "edit";
  saveToast: string;
  selectedNodePath: string | null;
  setSaveToast: (value: string) => void;
  setEditingBody: (value: string) => void;
  showTreeToggle: boolean;
  showNoFeatureState: boolean;
  autosaveLabel: string;
  updatedAt: string | null;
}) {
  const breadcrumbSegments = buildBreadcrumbSegments(activeFeatureName, selectedNodePath);
  const updatedLabel = formatUpdatedAt(updatedAt);
  return (
    <section className="detail-panel wiki-detail-panel">
      {saveToast ? (
        <div className="wiki-floating-toast" role="status">
          {saveToast}
        </div>
      ) : null}
      {document && routeMode === "view" ? (
        <WikiReader
          brokenImageTargets={brokenImageTargets}
          content={document.current_body_markdown ?? ""}
          header={
            // 报头并进正文那张纸：与正文共享左缘与纸宽，内部一道发丝线分隔，
            // 自身随文档滚动——它是这页文档的报头，而非浮在纸上方的另一块板。
            <header className="wiki-doc-masthead">
              <div className="wiki-doc-masthead-top">
                <div className="wiki-doc-masthead-lead">
                  {breadcrumbSegments.length > 0 ? (
                    <nav aria-label="文档路径" className="wiki-doc-breadcrumb">
                      {breadcrumbSegments.map((segment, index) => (
                        <span className="wiki-doc-crumb" key={`${segment}-${index}`}>
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
                  ) : null}
                  {updatedLabel ? (
                    <span className="wiki-doc-meta">
                      {breadcrumbSegments.length > 0 ? (
                        <span aria-hidden="true" className="wiki-doc-meta-dot">
                          ·
                        </span>
                      ) : null}
                      更新于 {updatedLabel}
                    </span>
                  ) : null}
                </div>
                <WikiFloatingActions
                  canEdit={canEdit}
                  onCopyLink={async () => {
                    await copyTextToClipboard(window.location.href);
                    setSaveToast("已复制当前 Wiki 链接");
                  }}
                  onEdit={onEdit}
                  onOpenDetail={onOpenDetail}
                  onOpenHistory={onOpenHistory}
                  onOpenImport={onOpenImport}
                  onOpenSources={onOpenSources}
                />
              </div>
            </header>
          }
          headingTarget={headingTarget}
          imageSrcMap={imageSrcMap}
          linkHrefMap={linkHrefMap}
        />
      ) : null}

      {document && routeMode === "edit" ? (
        <WikiEditor
          autosaveLabel={autosaveLabel}
          bodyMarkdown={editingBody}
          breadcrumbSegments={breadcrumbSegments}
          imageSrcMap={imageSrcMap}
          isDirty={editingBody !== (document.current_body_markdown ?? "")}
          linkHrefMap={linkHrefMap}
          onCancel={onRequestCancelEdit}
          onOpenHistory={onOpenHistory}
          onPublish={onSave}
          onToggleTree={onToggleTree}
          publishing={publishPending}
          setBodyMarkdown={setEditingBody}
          showTreeToggle={showTreeToggle}
          title={document.title}
        />
      ) : null}

      {report && routeMode === "view" ? (
        <WikiReportViewer
          onOpenFeaturePage={onOpenFeaturePage}
          report={report}
        />
      ) : null}

      {!document && !report && activeFeature && !hasSelection ? (
        featureHasDocuments ? (
          // 未选中任何节点、但特性下确有文档：引导去左侧选择，不预设给谁「建设」。
          <WikiEmptyState
            canCreate={false}
            description="从左侧目录展开特性，点选其下的文档即可在此阅读。"
            mode="select"
            title="选择一篇 Wiki 查看"
          />
        ) : activeFeatureIsHistory ? (
          // 历史特性是只读存档：不引导「建设」，也不给新建/导入入口。
          <WikiEmptyState
            canCreate={false}
            description="这是一个历史特性，Wiki 为只读存档，没有可查看的文档。"
            mode="history"
            title={
              activeFeatureName
                ? `「${activeFeatureName}」是历史特性`
                : "这是历史特性"
            }
          />
        ) : (
          // 特性确实还没有任何 Wiki：点名是哪个特性，再给出建设入口。
          <WikiEmptyState
            canCreate={canCreate}
            description="这个特性下还没有任何 Wiki 文档，新建一篇或导入现有资料即可开始。"
            mode="feature"
            onCreateDocument={canCreate ? onCreateDocument : undefined}
            onImport={canCreate ? onOpenImport : undefined}
            title={
              activeFeatureName
                ? `开始建设「${activeFeatureName}」的 Wiki`
                : "开始建设这个特性的 Wiki"
            }
          />
        )
      ) : null}

      {showNoFeatureState ? (
        <WikiEmptyState
          canCreate={false}
          description="当前还没有可用特性，先创建特性后再进入 Wiki。"
          mode="global"
          onCreateDocument={undefined}
          onImport={undefined}
          title="还没有可用特性"
        />
      ) : null}
    </section>
  );
}
