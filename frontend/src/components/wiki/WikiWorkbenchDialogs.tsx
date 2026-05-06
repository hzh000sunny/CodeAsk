import { WikiDetailDrawer } from "./WikiDetailDrawer";
import {
  WikiEditLeaveDialog,
  WikiMessageDialog,
  WikiNodeDeleteDialog,
  WikiNodeInputDialog,
} from "./WikiDialogs";
import { WikiImportDialog } from "./WikiImportDialog";
import { WikiMaintenanceActions } from "./WikiMaintenanceActions";
import { WikiNodeRestoreDialog } from "./WikiNodeRestoreDialog";
import { WikiSpaceRestoreDialog } from "./WikiSpaceRestoreDialog";
import { WikiSourcesDrawer } from "./WikiSourcesDrawer";
import { WikiVersionDrawer } from "./WikiVersionDrawer";
import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { isClearOnlyWikiNode } from "../../lib/wiki/system-node-actions";
import type {
  WikiDocumentDetailRead,
  WikiDocumentDiffRead,
  WikiDocumentVersionRead,
  WikiImportSessionItemsRead,
  WikiImportSessionRead,
  WikiImportSelectionItem,
  WikiSourceCreatePayload,
  WikiSourceRead,
  WikiSourceUpdatePayload,
} from "../../types/wiki";

type WikiNodeDialogState =
  | {
      kind: "create_document";
      parent: WikiTreeNodeRecord | null;
    }
  | {
      kind: "create_folder";
      parent: WikiTreeNodeRecord;
    }
  | {
      kind: "rename";
      node: WikiTreeNodeRecord;
    }
  | {
      kind: "delete";
      node: WikiTreeNodeRecord;
    }
  | null;

export { type WikiNodeDialogState };

export function WikiWorkbenchDialogs({
  actionPendingKey,
  bulkResolve,
  compareLoading,
  currentVersionId,
  deleteNodePending,
  detailOpen,
  diff,
  document,
  historyOpen,
  hasUnfinishedImportSession,
  importError,
  importOpen,
  importParentPath,
  importPending,
  importSession,
  importSessionItems,
  leaveDialogOpen,
  messageDialog,
  nodeDialog,
  nodeDialogError,
  path,
  publishPending,
  renameNodePending,
  restoreNodeCandidate,
  restoreNodePending,
  restoreSpaceCandidate,
  restoreSpacePending,
  sourceOpen,
  sourceRecentSyncedId,
  sources,
  sourcesLoading,
  sourceSubmitting,
  sourceSyncPendingId,
  versions,
  updatedAt,
  reindexCandidate,
  reindexPending,
  createNodePending,
  resolveNodePath,
  onCloseDetail,
  onCloseHistory,
  onCloseImport,
  onContinueImportInBackground,
  onCompareVersions,
  onConfirmDeleteNode,
  onConfirmLeaveCancel,
  onConfirmLeaveDiscard,
  onConfirmLeavePublish,
  onConfirmLeaveWithDraft,
  onDeleteNodeCancel,
  onDismissMessageDialog,
  onCloseSources,
  onCreateSource,
  onCloseRestoreNode,
  onCloseRestoreSpace,
  onCloseReindex,
  onConfirmReindex,
  onConfirmRestoreNode,
  onConfirmRestoreSpace,
  onImportCancel,
  onImportFilesSelected,
  onImportResolveItem,
  onImportRetryFailed,
  onImportRetryItem,
  onImportNodeCancel,
  onNodeDialogSubmit,
  onRollbackVersion,
  onSyncSource,
  onUpdateSource,
}: {
  compareLoading: boolean;
  currentVersionId: number | null;
  createNodePending: boolean;
  deleteNodePending: boolean;
  detailOpen: boolean;
  diff: WikiDocumentDiffRead | null;
  document: WikiDocumentDetailRead | null;
  actionPendingKey: string | null;
  bulkResolve: (action: "skip_all" | "overwrite_all") => void;
  hasUnfinishedImportSession: boolean;
  importError: string;
  historyOpen: boolean;
  importOpen: boolean;
  importParentPath: string | null;
  importPending: boolean;
  importSession: WikiImportSessionRead | null;
  importSessionItems: WikiImportSessionItemsRead | null;
  leaveDialogOpen: boolean;
  messageDialog: string;
  nodeDialog: WikiNodeDialogState;
  nodeDialogError: string;
  path: string | null;
  publishPending: boolean;
  renameNodePending: boolean;
  restoreNodeCandidate: WikiTreeNodeRecord | null;
  restoreNodePending: boolean;
  restoreSpaceCandidate: WikiTreeNodeRecord | null;
  restoreSpacePending: boolean;
  sourceOpen: boolean;
  sourceRecentSyncedId: number | null;
  sources: WikiSourceRead[];
  sourcesLoading: boolean;
  sourceSubmitting: boolean;
  sourceSyncPendingId: number | null;
  reindexCandidate: WikiTreeNodeRecord | null;
  reindexPending: boolean;
  updatedAt: string | null;
  versions: WikiDocumentVersionRead[];
  resolveNodePath: (node: WikiTreeNodeRecord | null | undefined) => string | null;
  onCloseDetail: () => void;
  onCloseHistory: () => void;
  onCloseImport: () => void;
  onContinueImportInBackground: () => void;
  onCompareVersions: (fromVersionId: number, toVersionId: number) => void;
  onConfirmDeleteNode: () => void;
  onConfirmLeaveCancel: () => void;
  onConfirmLeaveDiscard: () => void;
  onConfirmLeavePublish: () => void;
  onConfirmLeaveWithDraft: () => void;
  onDeleteNodeCancel: () => void;
  onDismissMessageDialog: () => void;
  onCloseSources: () => void;
  onCloseRestoreNode: () => void;
  onCloseRestoreSpace: () => void;
  onCloseReindex: () => void;
  onConfirmReindex: () => void;
  onConfirmRestoreNode: () => void;
  onConfirmRestoreSpace: () => void;
  onCreateSource: (payload: Omit<WikiSourceCreatePayload, "space_id">) => Promise<void>;
  onImportCancel: () => void;
  onImportFilesSelected: (payload: {
    files: File[];
    items: WikiImportSelectionItem[];
    mode: "markdown" | "directory";
  }) => void;
  onImportResolveItem: (itemId: number, action: "skip" | "overwrite") => void;
  onImportRetryFailed: () => void;
  onImportRetryItem: (itemId: number) => void;
  onImportNodeCancel: () => void;
  onNodeDialogSubmit: (value: string) => void;
  onRollbackVersion: (versionId: number) => void;
  onSyncSource: (sourceId: number) => void;
  onUpdateSource: (sourceId: number, payload: WikiSourceUpdatePayload) => Promise<void>;
}) {
  return (
    <>
      <WikiDetailDrawer
        document={document}
        onClose={onCloseDetail}
        open={detailOpen}
        path={path}
        updatedAt={updatedAt}
      />
      <WikiVersionDrawer
        currentVersionId={currentVersionId}
        diff={diff}
        loading={compareLoading}
        onClose={onCloseHistory}
        onCompare={onCompareVersions}
        onRollback={onRollbackVersion}
        open={historyOpen}
        versions={versions}
      />
      <WikiImportDialog
        actionPendingKey={actionPendingKey}
        errorMessage={importError}
        hasUnfinishedSession={hasUnfinishedImportSession}
        importTargetLabel={importParentPath}
        onBulkResolve={bulkResolve}
        onCancelImport={onImportCancel}
        onClose={onCloseImport}
        onContinueInBackground={onContinueImportInBackground}
        onFilesSelected={onImportFilesSelected}
        onResolveItem={onImportResolveItem}
        onRetryFailed={onImportRetryFailed}
        onRetryItem={onImportRetryItem}
        open={importOpen}
        pending={importPending}
        session={importSession}
        sessionItems={importSessionItems}
      />
      <WikiSourcesDrawer
        onClose={onCloseSources}
        onCreate={onCreateSource}
        onSync={onSyncSource}
        onUpdate={onUpdateSource}
        open={sourceOpen}
        recentSyncedSourceId={sourceRecentSyncedId}
        sources={sources}
        sourcesLoading={sourcesLoading}
        submitting={sourceSubmitting}
        syncPendingSourceId={sourceSyncPendingId}
      />
      {restoreNodeCandidate ? (
        <WikiNodeRestoreDialog
          isRestoring={restoreNodePending}
          nodeName={restoreNodeCandidate.name}
          onClose={onCloseRestoreNode}
          onRestore={onConfirmRestoreNode}
          path={resolveNodePath(restoreNodeCandidate) ?? restoreNodeCandidate.name}
        />
      ) : null}
      {restoreSpaceCandidate ? (
        <WikiSpaceRestoreDialog
          featureName={restoreSpaceCandidate.name}
          isRestoring={restoreSpacePending}
          onCancel={onCloseRestoreSpace}
          onConfirm={onConfirmRestoreSpace}
        />
      ) : null}
      {reindexCandidate ? (
        <WikiMaintenanceActions
          isRunning={reindexPending}
          nodeName={reindexCandidate.name}
          onCancel={onCloseReindex}
          onConfirm={onConfirmReindex}
          path={resolveNodePath(reindexCandidate) ?? reindexCandidate.name}
        />
      ) : null}
      {nodeDialog?.kind === "create_document" ? (
        <WikiNodeInputDialog
          confirmLabel="创建 Wiki"
          errorMessage={nodeDialogError}
          initialValue=""
          isSubmitting={createNodePending}
          modeLabel="document"
          onCancel={onImportNodeCancel}
          onSubmit={onNodeDialogSubmit}
          parentPath={resolveNodePath(nodeDialog.parent)}
          title="新建 Wiki"
        />
      ) : null}
      {nodeDialog?.kind === "create_folder" ? (
        <WikiNodeInputDialog
          confirmLabel="创建目录"
          errorMessage={nodeDialogError}
          initialValue=""
          isSubmitting={createNodePending}
          modeLabel="folder"
          onCancel={onImportNodeCancel}
          onSubmit={onNodeDialogSubmit}
          parentPath={resolveNodePath(nodeDialog.parent)}
          title="新建目录"
        />
      ) : null}
      {nodeDialog?.kind === "rename" ? (
        <WikiNodeInputDialog
          confirmLabel="保存名称"
          errorMessage={nodeDialogError}
          initialValue={nodeDialog.node.name}
          isSubmitting={renameNodePending}
          modeLabel="rename"
          onCancel={onImportNodeCancel}
          onSubmit={onNodeDialogSubmit}
          parentPath={resolveNodePath(nodeDialog.node)}
          title="重命名节点"
        />
      ) : null}
      {nodeDialog?.kind === "delete" ? (
        <WikiNodeDeleteDialog
          clearOnly={isClearOnlyWikiNode(nodeDialog.node)}
          errorMessage={nodeDialogError}
          isDeleting={deleteNodePending}
          nodeName={nodeDialog.node.name}
          onCancel={onDeleteNodeCancel}
          onConfirm={onConfirmDeleteNode}
          path={resolveNodePath(nodeDialog.node) ?? nodeDialog.node.name}
        />
      ) : null}
      {messageDialog ? (
        <WikiMessageDialog
          message={messageDialog}
          onClose={onDismissMessageDialog}
        />
      ) : null}
      {leaveDialogOpen ? (
        <WikiEditLeaveDialog
          isPublishing={publishPending}
          onCancel={onConfirmLeaveCancel}
          onDiscard={onConfirmLeaveDiscard}
          onLeaveWithDraft={onConfirmLeaveWithDraft}
          onPublish={onConfirmLeavePublish}
        />
      ) : null}
    </>
  );
}
