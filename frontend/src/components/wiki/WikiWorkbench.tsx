import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { deleteReport, getMe, listFeatures, listReports } from "../../lib/api";
import {
  createWikiNode,
  deleteWikiDraft,
  deleteWikiNode,
  getWikiDiff,
  getWikiSpaceByFeature,
  getWikiTree,
  publishWikiDocument,
  rollbackWikiVersion,
  updateWikiNode,
} from "../../lib/wiki/api";
import { buildWikiMarkdownLinkMaps } from "../../lib/wiki/markdown";
import { groupWikiSearchHits, injectWikiReportProjections } from "../../lib/wiki/presentation";
import { wikiQueryKeys } from "../../lib/wiki/query-keys";
import type { WikiRouteState } from "../../lib/wiki/routing";
import {
  buildWikiSystemClearPlan,
  isClearOnlyWikiNode,
} from "../../lib/wiki/system-node-actions";
import { findFeatureRootNode, findSystemRoleNode } from "../../lib/wiki/tree-selectors";
import {
  buildWikiNodeDisplayPath,
  findFirstReadableDocument,
  findNodeById,
  formatWikiStoredPath,
  type WikiTreeNodeRecord,
} from "../../lib/wiki/tree";
import type { WikiDocumentDiffRead } from "../../types/wiki";
import { messageFromError } from "../features/feature-utils";
import { WikiTreePane } from "./WikiTreePane";
import { WikiWorkbenchDialogs, type WikiNodeDialogState } from "./WikiWorkbenchDialogs";
import { WikiWorkspacePane } from "./WikiWorkspacePane";
import { useWikiDocument } from "./hooks/useWikiDocument";
import { useWikiDraftAutosave } from "./hooks/useWikiDraftAutosave";
import { useWikiImportSessionFlow } from "./hooks/useWikiImportSessionFlow";
import { useWikiNodeOrdering } from "./hooks/useWikiNodeOrdering";
import { useWikiReport, useWikiReportProjections } from "./hooks/useWikiReport";
import { useWikiSearch } from "./hooks/useWikiSearch";
import { useWikiTree } from "./hooks/useWikiTree";
import { useWikiTreeLayout } from "./hooks/useWikiTreeLayout";

export function WikiWorkbench({
  backgroundImportSession,
  onBackgroundImportChange,
  onImportNavigationGuardChange,
  onOpenFeature,
  onRouteChange,
  routeState,
}: {
  backgroundImportSession: { sessionId: number; featureId: number | null } | null;
  onBackgroundImportChange: (session: { sessionId: number; featureId: number | null } | null) => void;
  onImportNavigationGuardChange: (
    guard:
      | {
          blocking: boolean;
          continueInBackground: () => void;
          cancelImport: () => Promise<boolean>;
        }
      | null,
  ) => void;
  onOpenFeature: (featureId: number) => void;
  onRouteChange: (patch: Partial<WikiRouteState>) => void;
  routeState: WikiRouteState;
}) {
  const queryClient = useQueryClient();
  const { treeCollapsed, setTreeCollapsed, startTreeResize, workspaceStyle } =
    useWikiTreeLayout(routeState.mode);
  const [search, setSearch] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [saveToast, setSaveToast] = useState("");
  const [messageDialog, setMessageDialog] = useState("");
  const [editingBody, setEditingBody] = useState("");
  const [versionDiff, setVersionDiff] = useState<WikiDocumentDiffRead | null>(null);
  const [nodeDialog, setNodeDialog] = useState<WikiNodeDialogState>(null);
  const [nodeDialogError, setNodeDialogError] = useState("");
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
  const previousDocumentIdRef = useRef<number | null>(null);
  const previousModeRef = useRef<WikiRouteState["mode"]>(routeState.mode);

  const featureQuery = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const authQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
  });
  const features = featureQuery.data ?? [];
  const fallbackFeatureId = features[0]?.id ?? null;
  const activeFeatureId = routeState.featureId ?? fallbackFeatureId;
  const activeListedFeature =
    features.find((feature) => feature.id === activeFeatureId) ?? null;

  const treeQuery = useWikiTree(null, routeState.nodeId);
  const activeSpaceQuery = useQuery({
    queryKey: [...wikiQueryKeys.all, "space", activeFeatureId],
    queryFn: () => getWikiSpaceByFeature(activeFeatureId as number),
    enabled: activeFeatureId != null,
  });
  const reportProjectionQuery = useWikiReportProjections(activeFeatureId);
  const tree = useMemo(
    () =>
      injectWikiReportProjections(
        treeQuery.tree,
        reportProjectionQuery.data?.items ?? [],
        activeFeatureId,
      ),
    [activeFeatureId, reportProjectionQuery.data?.items, treeQuery.tree],
  );
  const activeFeatureRoot = useMemo(
    () => findFeatureRootNode(tree, activeFeatureId),
    [activeFeatureId, tree],
  );
  const activeFeatureTree = useMemo(
    () => (activeFeatureRoot ? [activeFeatureRoot] : []),
    [activeFeatureRoot],
  );
  const selectedNode = useMemo(
    () => findNodeById(tree, routeState.nodeId),
    [routeState.nodeId, tree],
  );
  const selectedNodeDisplayPath = useMemo(
    () =>
      buildWikiNodeDisplayPath(tree, routeState.nodeId) ??
      formatWikiStoredPath(selectedNode?.path ?? null),
    [routeState.nodeId, selectedNode?.path, tree],
  );
  const firstDocument = useMemo(
    () => findFirstReadableDocument(activeFeatureTree),
    [activeFeatureTree],
  );
  const documentEnabled = selectedNode?.type === "document";
  const reportEnabled = selectedNode?.type === "report_ref";
  const { currentVersion, documentQuery, versionsQuery } = useWikiDocument(
    selectedNode?.id ?? null,
    Boolean(documentEnabled),
  );
  const reportQuery = useWikiReport(selectedNode?.id ?? null, Boolean(reportEnabled));
  const searchQuery = useWikiSearch(activeFeatureId, search);
  const searchGroups = useMemo(
    () =>
      groupWikiSearchHits(searchQuery.data?.items ?? []).map((group) => ({
        ...group,
        items: group.items.map((item) => ({
          ...item,
          path:
            buildWikiNodeDisplayPath(tree, item.node_id) ??
            formatWikiStoredPath(item.path) ??
            item.path,
        })),
      })),
    [searchQuery.data?.items, tree],
  );
  const knowledgeRoot = useMemo(
    () => findSystemRoleNode(activeFeatureTree, "knowledge_base"),
    [activeFeatureTree],
  );
  const canManageFeature = Boolean(activeFeatureId != null && authQuery.data);
  const activeSpace = activeSpaceQuery.data ?? treeQuery.space ?? null;
  const drawer = routeState.drawer;
  const nodeOrdering = useWikiNodeOrdering({
    onError: setMessageDialog,
    onSuccess: setSaveToast,
    queryClient,
    tree,
  });

  async function invalidateActiveFeatureTree(featureId: number) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(null) }),
      queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(featureId) }),
    ]);
  }

  async function invalidateFeatureDerivedViews(featureId: number | null) {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["reports", featureId] }),
      queryClient.invalidateQueries({ queryKey: wikiQueryKeys.reportProjections(featureId) }),
      queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "report"] }),
      queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "search"] }),
    ]);
  }

  const importFlow = useWikiImportSessionFlow({
    activeFeatureId,
    activeSpace,
    backgroundSession: backgroundImportSession,
    knowledgeRoot,
    onBackgroundSessionChange: onBackgroundImportChange,
    queryClient,
    onRouteChange,
    invalidateActiveFeatureTree,
    onCompleted: () => setSaveToast("Wiki 导入完成"),
  });

  useEffect(() => {
    onImportNavigationGuardChange({
      blocking: drawer === "import" && importFlow.hasUnfinishedSession,
      continueInBackground: importFlow.continueImportInBackground,
      cancelImport: importFlow.cancelImport,
    });
    return () => {
      onImportNavigationGuardChange(null);
    };
  }, [
    drawer,
    importFlow.cancelImport,
    importFlow.continueImportInBackground,
    importFlow.hasUnfinishedSession,
    onImportNavigationGuardChange,
  ]);

  useEffect(() => {
    if (features.length === 0 || routeState.featureId != null) {
      return;
    }
    onRouteChange({
      featureId: features[0].id,
      nodeId: null,
      heading: null,
      mode: "view",
      drawer: null,
    });
  }, [features, onRouteChange, routeState.featureId]);

  useEffect(() => {
    if (!tree.length || activeFeatureId == null) {
      return;
    }
    if (routeState.nodeId != null && selectedNode) {
      return;
    }
    if (firstDocument) {
      if (routeState.featureId === activeFeatureId && routeState.nodeId === firstDocument.id) {
        return;
      }
      onRouteChange({ featureId: activeFeatureId, nodeId: firstDocument.id, heading: null });
      return;
    }
    if (routeState.featureId === activeFeatureId && routeState.nodeId == null) {
      return;
    }
    onRouteChange({ featureId: activeFeatureId, nodeId: null, heading: null });
  }, [
    activeFeatureId,
    firstDocument,
    onRouteChange,
    routeState.featureId,
    routeState.nodeId,
    selectedNode,
    tree.length,
  ]);

  useEffect(() => {
    const nextExpanded = new Set<number>();
    nextExpanded.add(-1);
    if (activeFeatureRoot) {
      nextExpanded.add(activeFeatureRoot.id);
    }
    if (knowledgeRoot) {
      nextExpanded.add(knowledgeRoot.id);
    }
    setExpandedIds(nextExpanded);
  }, [activeFeatureRoot, knowledgeRoot]);

  useEffect(() => {
    if (reportEnabled && routeState.mode === "edit") {
      onRouteChange({ mode: "view", heading: null });
    }
  }, [onRouteChange, reportEnabled, routeState.mode]);

  const documentBaselineBody = useMemo(
    () =>
      documentQuery.data == null
        ? ""
        : documentQuery.data.draft_body_markdown ??
          documentQuery.data.current_body_markdown ??
          "",
    [
      documentQuery.data?.document_id,
      documentQuery.data?.draft_body_markdown,
      documentQuery.data?.current_body_markdown,
    ],
  );

  useEffect(() => {
    const currentDocumentId = documentQuery.data?.document_id ?? null;
    const documentChanged =
      currentDocumentId != null && currentDocumentId !== previousDocumentIdRef.current;
    const enteringEdit = routeState.mode === "edit" && previousModeRef.current !== "edit";

    if (documentQuery.data && (documentChanged || enteringEdit)) {
      setEditingBody(documentBaselineBody);
    }

    previousDocumentIdRef.current = currentDocumentId;
    previousModeRef.current = routeState.mode;
  }, [documentBaselineBody, documentQuery.data, routeState.mode]);

  useEffect(() => {
    if (!saveToast) {
      return;
    }
    const timer = window.setTimeout(() => setSaveToast(""), 1600);
    return () => window.clearTimeout(timer);
  }, [saveToast]);

  useEffect(() => {
    setNodeDialogError("");
  }, [nodeDialog]);

  const publishMutation = useMutation({
    mutationFn: async () => {
      if (selectedNode == null) {
        return null;
      }
      return publishWikiDocument(selectedNode.id, editingBody);
    },
    onSuccess: (data) => {
      if (!selectedNode || !data) {
        return;
      }
      setSaveToast("保存成功");
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(selectedNode.id) });
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.versions(selectedNode.id) });
      onRouteChange({ mode: "view", heading: null });
    },
    onError: (error) => {
      setMessageDialog(`保存失败：${messageFromError(error)}`);
    },
  });

  const draftAutosave = useWikiDraftAutosave({
    baselineBody: documentBaselineBody,
    bodyMarkdown: editingBody,
    enabled: routeState.mode === "edit" && selectedNode?.type === "document",
    nodeId: selectedNode?.id ?? null,
    onSaved: (document) => {
      if (!selectedNode || !document) {
        return;
      }
      queryClient.setQueryData(wikiQueryKeys.document(selectedNode.id), document);
    },
  });

  const createNodeMutation = useMutation({
    mutationFn: async ({
      name,
      parentId,
      type,
    }: {
      name: string;
      parentId: number | null;
      type: "folder" | "document";
    }) => {
      if (!activeSpace) {
        return null;
      }
      return createWikiNode({
        space_id: activeSpace.id,
        parent_id: parentId,
        type,
        name,
      });
    },
  });

  const renameNodeMutation = useMutation({
    mutationFn: async ({ nodeId, name }: { nodeId: number; name: string }) =>
      updateWikiNode(nodeId, { name }),
  });

  const deleteNodeMutation = useMutation({
    mutationFn: async (nodeId: number) => deleteWikiNode(nodeId),
  });

  const clearNodeContentsMutation = useMutation({
    mutationFn: async (node: WikiTreeNodeRecord) => {
      const reports = activeFeatureId != null ? await listReports(activeFeatureId) : [];
      const plan = buildWikiSystemClearPlan(node, reports);
      await Promise.all([
        ...plan.nodeIds.map((nodeId) => deleteWikiNode(nodeId)),
        ...plan.reportIds.map((reportId) => deleteReport(reportId)),
      ]);
      return plan;
    },
  });

  const compareMutation = useMutation({
    mutationFn: async ({
      fromVersionId,
      toVersionId,
    }: {
      fromVersionId: number;
      toVersionId: number;
    }) => {
      if (!selectedNode) {
        return null;
      }
      return getWikiDiff(selectedNode.id, fromVersionId, toVersionId);
    },
    onSuccess: (data) => {
      setVersionDiff(data);
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: async (versionId: number) => {
      if (!selectedNode) {
        return null;
      }
      return rollbackWikiVersion(selectedNode.id, versionId);
    },
    onSuccess: () => {
      if (!selectedNode) {
        return;
      }
      setSaveToast("已回滚到指定版本并生成新快照");
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(selectedNode.id) });
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.versions(selectedNode.id) });
    },
    onError: (error) => {
      setMessageDialog(`回滚失败：${messageFromError(error)}`);
    },
  });

  const imageAndLinkMaps = useMemo(
    () =>
      buildWikiMarkdownLinkMaps(
        documentQuery.data?.resolved_refs_json ?? [],
        activeFeatureId,
      ),
    [activeFeatureId, documentQuery.data?.resolved_refs_json],
  );
  const brokenImageTargets = useMemo(
    () =>
      new Set(
        (documentQuery.data?.broken_refs_json?.assets ?? []).map((item) => item.target),
      ),
    [documentQuery.data?.broken_refs_json?.assets],
  );
  const canEdit = Boolean(documentQuery.data?.permissions.write);

  function resolveNodePath(node: WikiTreeNodeRecord | null | undefined) {
    if (!node) {
      return null;
    }
    return buildWikiNodeDisplayPath(tree, node.id) ?? formatWikiStoredPath(node.path) ?? node.name;
  }

  function openCreateDocumentDialog(parent?: WikiTreeNodeRecord | null) {
    setNodeDialog({
      kind: "create_document",
      parent: parent ?? knowledgeRoot,
    });
  }

  function openCreateFolderDialog(parent: WikiTreeNodeRecord) {
    setNodeDialog({
      kind: "create_folder",
      parent,
    });
  }

  function openRenameDialog(node: WikiTreeNodeRecord) {
    setNodeDialog({
      kind: "rename",
      node,
    });
  }

  function openDeleteDialog(node: WikiTreeNodeRecord) {
    setNodeDialog({
      kind: "delete",
      node,
    });
  }

  async function handleNodeDialogSubmit(value: string) {
    if (activeFeatureId == null || !nodeDialog) {
      return;
    }
    try {
      if (nodeDialog.kind === "rename") {
        await renameNodeMutation.mutateAsync({
          nodeId: nodeDialog.node.id,
          name: value.trim(),
        });
        await invalidateActiveFeatureTree(activeFeatureId);
        if (nodeDialog.node.type === "document") {
          await queryClient.invalidateQueries({
            queryKey: wikiQueryKeys.document(nodeDialog.node.id),
          });
        }
        setSaveToast("Wiki 节点已重命名");
        setNodeDialog(null);
        return;
      }
      if (nodeDialog.kind !== "create_document" && nodeDialog.kind !== "create_folder") {
        return;
      }

      const parent = nodeDialog.parent;
      const parentId = parent?.id ?? null;
      const type = nodeDialog.kind === "create_folder" ? "folder" : "document";
      const created = await createNodeMutation.mutateAsync({
        name: value.trim(),
        parentId,
        type,
      });
      await invalidateActiveFeatureTree(activeFeatureId);
      if (parentId != null) {
        setExpandedIds((current) => new Set(current).add(parentId));
      }
      setNodeDialog(null);
      if (!created) {
        return;
      }
      if (type === "document") {
        setSaveToast("已创建新的 Wiki 文档");
        onRouteChange({
          featureId: activeFeatureId,
          nodeId: created.id,
          heading: null,
          mode: "edit",
          drawer: null,
        });
      } else {
        setSaveToast("已创建新的目录");
      }
    } catch (error) {
      setNodeDialogError(messageFromError(error));
    }
  }

  async function handleDeleteNode() {
    if (activeFeatureId == null || nodeDialog?.kind !== "delete") {
      return;
    }
    try {
      const deletingNode = nodeDialog.node;
      const clearOnly = isClearOnlyWikiNode(deletingNode);
      if (clearOnly) {
        await clearNodeContentsMutation.mutateAsync(deletingNode);
      } else {
        await deleteNodeMutation.mutateAsync(deletingNode.id);
      }

      setNodeDialog(null);
      setSaveToast(clearOnly ? "目录内容已清空" : "Wiki 节点已删除");

      const clearsWholeFeature =
        clearOnly &&
        (deletingNode.system_role === "feature_space_current" ||
          deletingNode.system_role === "feature_space_history");
      if (
        (clearsWholeFeature &&
          selectedNode?.feature_id != null &&
          selectedNode.feature_id === deletingNode.feature_id) ||
        (selectedNode &&
          (selectedNode.id === deletingNode.id ||
            selectedNode.path.startsWith(`${deletingNode.path}/`)))
      ) {
        onRouteChange({ nodeId: null, heading: null, mode: "view", drawer: null });
      }

      await invalidateActiveFeatureTree(activeFeatureId);
      await invalidateFeatureDerivedViews(activeFeatureId);
    } catch (error) {
      setNodeDialogError(messageFromError(error));
    }
  }

  async function discardDraftAndLeave() {
    if (!selectedNode || !documentQuery.data) {
      return;
    }
    try {
      await deleteWikiDraft(selectedNode.id);
      draftAutosave.markSavedBaseline(documentQuery.data.current_body_markdown ?? "");
      setEditingBody(documentQuery.data.current_body_markdown ?? "");
      setLeaveDialogOpen(false);
      onRouteChange({ mode: "view", heading: null });
      setSaveToast("已丢弃当前草稿");
    } catch (error) {
      setMessageDialog(`丢弃草稿失败：${messageFromError(error)}`);
    }
  }

  return (
    <section
      className="workspace wiki-workspace"
      data-list-collapsed={treeCollapsed}
      style={workspaceStyle}
    >
      <WikiTreePane
        canManageFeature={canManageFeature}
        collapsed={treeCollapsed}
        expandedIds={expandedIds}
        onCreateDocument={(parent) => openCreateDocumentDialog(parent)}
        onCreateFolder={openCreateFolderDialog}
        onDeleteNode={openDeleteDialog}
        onImport={() => importFlow.openImportDialog(knowledgeRoot)}
        onImportNode={(node) => importFlow.openImportDialog(node)}
        onMoveDownNode={nodeOrdering.moveDown}
        onMoveNodeRequest={nodeOrdering.moveNode}
        onMoveUpNode={nodeOrdering.moveUp}
        onRenameNode={openRenameDialog}
        onResizeFromCollapseButton={(event) =>
          startTreeResize(event, {
            onClick: () => setTreeCollapsed((value) => !value),
          })
        }
        onSelectSearchHit={(hit) => {
          onRouteChange({
            featureId: hit.feature_id ?? routeState.featureId,
            nodeId: hit.node_id,
            heading: hit.heading_path ?? null,
            mode: "view",
            drawer: null,
          });
        }}
        onSelectNode={(node: WikiTreeNodeRecord) => {
          if (
            node.feature_id != null &&
            node.feature_id !== routeState.featureId &&
            (node.type === "folder" || node.type === "document" || node.type === "report_ref")
          ) {
            onRouteChange({
              featureId: node.feature_id,
              nodeId: null,
              heading: null,
              mode: "view",
              drawer: null,
            });
            return;
          }
          if (node.type === "document" || node.type === "report_ref") {
            onRouteChange({
              featureId: node.feature_id ?? routeState.featureId,
              nodeId: node.id,
              heading: null,
              mode: "view",
              drawer: null,
            });
          }
        }}
        onToggleCollapsed={() => setTreeCollapsed((value) => !value)}
        onToggleNode={(nodeId) =>
          setExpandedIds((current) => {
            const next = new Set(current);
            if (next.has(nodeId)) {
              next.delete(nodeId);
            } else {
              next.add(nodeId);
            }
            return next;
          })
        }
        roots={tree}
        search={search}
        searchGroups={searchGroups}
        searchLoading={searchQuery.isLoading}
        selectedNodeId={selectedNode?.id ?? null}
        setSearch={setSearch}
      />
      {!treeCollapsed ? (
        <button
          aria-label="调整 Wiki 目录宽度"
          aria-orientation="vertical"
          className="wiki-pane-resizer"
          onMouseDown={(event) => startTreeResize(event)}
          role="separator"
          type="button"
        />
      ) : (
        <div aria-hidden="true" className="wiki-pane-resizer-spacer" />
      )}
      <WikiWorkspacePane
        activeFeature={activeFeatureId != null ? { id: activeFeatureId } : null}
        autosaveLabel={
          draftAutosave.autosaveStatus === "saving"
            ? "正在自动保存草稿..."
            : draftAutosave.autosaveStatus === "saved"
              ? "草稿已自动保存"
              : "编辑中 · 自动草稿已开启"
        }
        brokenImageTargets={brokenImageTargets}
        canCreate={canManageFeature}
        canEdit={canEdit}
        document={documentQuery.data ?? null}
        editingBody={editingBody}
        headingTarget={routeState.heading}
        imageSrcMap={imageAndLinkMaps.imageSrcMap}
        linkHrefMap={imageAndLinkMaps.linkHrefMap}
        onCreateDocument={canManageFeature ? () => openCreateDocumentDialog(knowledgeRoot) : undefined}
        onEdit={() => onRouteChange({ mode: "edit", drawer: null, heading: null })}
        onOpenDetail={() => onRouteChange({ drawer: "detail" })}
        onOpenFeaturePage={() => {
          if (activeListedFeature) {
            onOpenFeature(activeListedFeature.id);
          }
        }}
        onOpenHistory={() => onRouteChange({ drawer: "history" })}
        onOpenImport={() => importFlow.openImportDialog(knowledgeRoot)}
        onRequestCancelEdit={() => {
          const publishedBody = documentQuery.data?.current_body_markdown ?? "";
          const hasDraftChanges =
            documentQuery.data?.draft_body_markdown != null &&
            documentQuery.data.draft_body_markdown !== publishedBody;
          if (selectedNode && !hasDraftChanges && editingBody === publishedBody) {
            onRouteChange({ mode: "view", heading: null });
            return;
          }
          setLeaveDialogOpen(true);
        }}
        onSave={() => publishMutation.mutate()}
        onToggleTree={() => setTreeCollapsed((value) => !value)}
        publishPending={publishMutation.isPending}
        report={reportQuery.data ?? null}
        routeMode={routeState.mode}
        saveToast={saveToast}
        selectedNodePath={selectedNodeDisplayPath}
        setSaveToast={setSaveToast}
        setEditingBody={setEditingBody}
        showNoFeatureState={activeFeatureId == null && !featureQuery.isLoading}
        showTreeToggle={treeCollapsed}
      />
      <WikiWorkbenchDialogs
        actionPendingKey={importFlow.actionPendingKey}
        bulkResolve={importFlow.bulkResolve}
        compareLoading={compareMutation.isPending}
        createNodePending={createNodeMutation.isPending}
        currentVersionId={currentVersion?.id ?? documentQuery.data?.current_version_id ?? null}
        deleteNodePending={deleteNodeMutation.isPending || clearNodeContentsMutation.isPending}
        detailOpen={drawer === "detail"}
        diff={versionDiff}
        document={documentQuery.data ?? null}
        hasUnfinishedImportSession={importFlow.hasUnfinishedSession}
        historyOpen={drawer === "history"}
        importError={importFlow.importError}
        importOpen={drawer === "import"}
        importParentPath={resolveNodePath(importFlow.importParent) ?? resolveNodePath(knowledgeRoot)}
        importPending={importFlow.pending}
        importSession={importFlow.importSession}
        importSessionItems={importFlow.importSessionItems}
        leaveDialogOpen={leaveDialogOpen}
        messageDialog={messageDialog}
        nodeDialog={nodeDialog}
        nodeDialogError={nodeDialogError}
        onCloseDetail={() => onRouteChange({ drawer: null })}
        onCloseHistory={() => onRouteChange({ drawer: null })}
        onCloseImport={importFlow.closeImportDialog}
        onContinueImportInBackground={importFlow.continueImportInBackground}
        onCompareVersions={(fromVersionId, toVersionId) =>
          compareMutation.mutate({ fromVersionId, toVersionId })
        }
        onConfirmDeleteNode={handleDeleteNode}
        onConfirmLeaveCancel={() => setLeaveDialogOpen(false)}
        onConfirmLeaveDiscard={discardDraftAndLeave}
        onConfirmLeavePublish={() => {
          setLeaveDialogOpen(false);
          publishMutation.mutate();
        }}
        onConfirmLeaveWithDraft={() => {
          setLeaveDialogOpen(false);
          onRouteChange({ mode: "view", heading: null });
        }}
        onDeleteNodeCancel={() => setNodeDialog(null)}
        onDismissMessageDialog={() => setMessageDialog("")}
        onImportCancel={importFlow.cancelImport}
        onImportFilesSelected={importFlow.onFilesSelected}
        onImportResolveItem={importFlow.resolveItem}
        onImportRetryFailed={importFlow.retryFailed}
        onImportRetryItem={importFlow.retryItem}
        onImportNodeCancel={() => setNodeDialog(null)}
        onNodeDialogSubmit={handleNodeDialogSubmit}
        onRollbackVersion={(versionId) => rollbackMutation.mutate(versionId)}
        path={selectedNodeDisplayPath}
        publishPending={publishMutation.isPending}
        renameNodePending={renameNodeMutation.isPending}
        resolveNodePath={resolveNodePath}
        updatedAt={selectedNode?.updated_at ?? null}
        versions={versionsQuery.data?.versions ?? []}
      />
    </section>
  );
}
