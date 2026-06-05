import type { WikiDocumentDetailRead, WikiReportDetailRead } from "../../types/wiki";
import { copyTextToClipboard } from "../session/session-clipboard";
import { WikiEditor } from "./WikiEditor";
import { WikiEmptyState } from "./WikiEmptyState";
import { WikiFloatingActions } from "./WikiFloatingActions";
import { WikiReader } from "./WikiReader";
import { WikiReportViewer } from "./WikiReportViewer";

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
  featureHasDocuments,
  hasSelection,
}: {
  activeFeature: { id: number } | null;
  activeFeatureName: string | null;
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
}) {
  return (
    <section className="detail-panel wiki-detail-panel">
      {saveToast ? (
        <div className="wiki-floating-toast" role="status">
          {saveToast}
        </div>
      ) : null}
      {document && routeMode === "view" ? (
        <>
          <div className="page-header compact wiki-page-header">
            <div>
              <h1>{document.title}</h1>
              <p>{selectedNodePath}</p>
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
          <WikiReader
            brokenImageTargets={brokenImageTargets}
            content={document.current_body_markdown ?? ""}
            headingTarget={headingTarget}
            imageSrcMap={imageSrcMap}
            linkHrefMap={linkHrefMap}
          />
        </>
      ) : null}

      {document && routeMode === "edit" ? (
        <WikiEditor
          autosaveLabel={autosaveLabel}
          bodyMarkdown={editingBody}
          imageSrcMap={imageSrcMap}
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
