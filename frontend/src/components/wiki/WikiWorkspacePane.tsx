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
}: {
  activeFeature: { id: number } | null;
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

      {!document && !report && activeFeature ? (
        <WikiEmptyState
          canCreate={canCreate}
          description="当前特性还没有 Wiki 文档，或当前选择的节点不是文档。"
          mode="feature"
          onCreateDocument={canCreate ? onCreateDocument : undefined}
          onImport={canCreate ? onOpenImport : undefined}
          title="开始建设这个特性的 Wiki"
        />
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
