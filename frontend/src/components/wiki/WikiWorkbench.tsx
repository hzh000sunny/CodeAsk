import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getMe, listFeatures } from "../../lib/api";
import {
  applyWikiImportJob,
  createWikiImportJob,
  createWikiNode,
  deleteWikiNode,
  deleteWikiDraft,
  getWikiDiff,
  listWikiImportJobItems,
  preflightWikiImport,
  publishWikiDocument,
  rollbackWikiVersion,
  updateWikiNode,
} from "../../lib/wiki/api";
import { buildWikiMarkdownLinkMaps } from "../../lib/wiki/markdown";
import { groupWikiSearchHits, injectWikiReportProjections } from "../../lib/wiki/presentation";
import { wikiQueryKeys } from "../../lib/wiki/query-keys";
import type { WikiRouteState } from "../../lib/wiki/routing";
import {
  findFirstReadableDocument,
  findNodeById,
  type WikiTreeNodeRecord,
} from "../../lib/wiki/tree";
import type {
  WikiDocumentDiffRead,
  WikiImportJobItemsRead,
  WikiImportJobRead,
  WikiImportPreflightRead,
} from "../../types/wiki";
import { messageFromError } from "../features/feature-utils";
import {
  WikiEditLeaveDialog,
  WikiNodeDeleteDialog,
  WikiNodeInputDialog,
} from "./WikiDialogs";
import { WikiDetailDrawer } from "./WikiDetailDrawer";
import { WikiEditor } from "./WikiEditor";
import { WikiEmptyState } from "./WikiEmptyState";
import { WikiFloatingActions } from "./WikiFloatingActions";
import { WikiImportDialog } from "./WikiImportDialog";
import { WikiReader } from "./WikiReader";
import { WikiReportViewer } from "./WikiReportViewer";
import { WikiTreePane } from "./WikiTreePane";
import { WikiVersionDrawer } from "./WikiVersionDrawer";
import { useWikiDocument } from "./hooks/useWikiDocument";
import { useWikiDraftAutosave } from "./hooks/useWikiDraftAutosave";
import { useWikiReport, useWikiReportProjections } from "./hooks/useWikiReport";
import { useWikiSearch } from "./hooks/useWikiSearch";
import { useWikiTree } from "./hooks/useWikiTree";
import { copyTextToClipboard } from "../session/session-clipboard";

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

export function WikiWorkbench({
  onOpenFeature,
  onRouteChange,
  routeState,
}: {
  onOpenFeature: (featureId: number) => void;
  onRouteChange: (patch: Partial<WikiRouteState>) => void;
  routeState: WikiRouteState;
}) {
  const queryClient = useQueryClient();
  const [treeCollapsed, setTreeCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [banner, setBanner] = useState("");
  const [editingBody, setEditingBody] = useState("");
  const [versionDiff, setVersionDiff] = useState<WikiDocumentDiffRead | null>(null);
  const [importPreflight, setImportPreflight] = useState<WikiImportPreflightRead | null>(null);
  const [importJob, setImportJob] = useState<WikiImportJobRead | null>(null);
  const [importItems, setImportItems] = useState<WikiImportJobItemsRead | null>(null);
  const [selectedImportFiles, setSelectedImportFiles] = useState<File[]>([]);
  const [nodeDialog, setNodeDialog] = useState<WikiNodeDialogState>(null);
  const [nodeDialogError, setNodeDialogError] = useState("");
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false);
  const featureQuery = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const authQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
  });
  const features = featureQuery.data ?? [];
  const activeFeature =
    features.find((feature) => feature.id === routeState.featureId) ?? features[0] ?? null;
  const treeQuery = useWikiTree(activeFeature?.id ?? null, routeState.nodeId);
  const reportProjectionQuery = useWikiReportProjections(activeFeature?.id ?? null);
  const tree = useMemo(
    () => injectWikiReportProjections(treeQuery.tree, reportProjectionQuery.data?.items ?? []),
    [reportProjectionQuery.data?.items, treeQuery.tree],
  );
  const selectedNode = useMemo(
    () => findNodeById(tree, routeState.nodeId),
    [routeState.nodeId, tree],
  );
  const firstDocument = useMemo(() => findFirstReadableDocument(tree), [tree]);
  const documentEnabled = selectedNode?.type === "document";
  const reportEnabled = selectedNode?.type === "report_ref";
  const { currentVersion, documentQuery, versionsQuery } = useWikiDocument(
    selectedNode?.id ?? null,
    Boolean(documentEnabled),
  );
  const reportQuery = useWikiReport(selectedNode?.id ?? null, Boolean(reportEnabled));
  const searchQuery = useWikiSearch(activeFeature?.id ?? null, search);
  const searchGroups = useMemo(
    () => groupWikiSearchHits(searchQuery.data?.items ?? []),
    [searchQuery.data?.items],
  );
  const knowledgeRoot = useMemo(
    () => tree.find((node) => node.system_role === "knowledge_base") ?? null,
    [tree],
  );
  const canManageFeature = Boolean(
    activeFeature &&
      authQuery.data &&
      (authQuery.data.role === "admin" ||
        authQuery.data.subject_id === activeFeature.owner_subject_id),
  );

  useEffect(() => {
    if (features.length === 0 || routeState.featureId != null) {
      return;
    }
    onRouteChange({
      featureId: features[0].id,
      nodeId: null,
      mode: "view",
      drawer: null,
    });
  }, [features, onRouteChange, routeState.featureId]);

  useEffect(() => {
    if (!tree.length || !activeFeature) {
      return;
    }
    if (routeState.nodeId != null && selectedNode) {
      return;
    }
    if (firstDocument) {
      onRouteChange({ featureId: activeFeature.id, nodeId: firstDocument.id });
      return;
    }
    onRouteChange({ featureId: activeFeature.id, nodeId: null });
  }, [
    activeFeature,
    firstDocument,
    onRouteChange,
    routeState.nodeId,
    selectedNode,
    tree,
  ]);

  useEffect(() => {
    const nextExpanded = new Set<number>();
    for (const root of tree) {
      if (root.system_role === "knowledge_base") {
        nextExpanded.add(root.id);
      }
    }
    setExpandedIds(nextExpanded);
  }, [activeFeature?.id, tree]);

  useEffect(() => {
    if (routeState.mode === "edit") {
      setTreeCollapsed(true);
    }
  }, [routeState.mode]);

  useEffect(() => {
    if (reportEnabled && routeState.mode === "edit") {
      onRouteChange({ mode: "view" });
    }
  }, [onRouteChange, reportEnabled, routeState.mode]);

  useEffect(() => {
    if (!documentQuery.data) {
      return;
    }
    const nextBody =
      documentQuery.data.draft_body_markdown ??
      documentQuery.data.current_body_markdown ??
      "";
    setEditingBody(nextBody);
  }, [documentQuery.data?.document_id, documentQuery.data?.draft_body_markdown, documentQuery.data?.current_body_markdown]);

  useEffect(() => {
    if (!banner) {
      return;
    }
    const timer = window.setTimeout(() => {
      setBanner("");
    }, 2400);
    return () => {
      window.clearTimeout(timer);
    };
  }, [banner]);

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
      setBanner("Wiki 已发布");
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(selectedNode.id) });
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.versions(selectedNode.id) });
      onRouteChange({ mode: "view" });
    },
    onError: (error) => {
      setBanner(`发布失败：${messageFromError(error)}`);
    },
  });

  const draftAutosave = useWikiDraftAutosave({
    bodyMarkdown: editingBody,
    enabled: routeState.mode === "edit" && selectedNode?.type === "document",
    nodeId: selectedNode?.id ?? null,
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
      if (!treeQuery.space) {
        return null;
      }
      return createWikiNode({
        space_id: treeQuery.space.id,
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

  const compareMutation = useMutation({
    mutationFn: async ({ fromVersionId, toVersionId }: { fromVersionId: number; toVersionId: number }) => {
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
      setBanner("已回滚到指定版本并生成新快照");
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(selectedNode.id) });
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.versions(selectedNode.id) });
    },
    onError: (error) => {
      setBanner(`回滚失败：${messageFromError(error)}`);
    },
  });

  const importMutation = useMutation({
    mutationFn: async (files: File[]) => {
      if (!treeQuery.space) {
        return null;
      }
      return preflightWikiImport({
        spaceId: treeQuery.space.id,
        parentId: null,
        files,
      });
    },
    onSuccess: (data) => {
      setImportPreflight(data);
      setImportJob(null);
      setImportItems(null);
    },
    onError: (error) => {
      setBanner(`导入预检查失败：${messageFromError(error)}`);
    },
  });

  const createImportJobMutation = useMutation({
    mutationFn: async (files: File[]) => {
      if (!treeQuery.space) {
        return null;
      }
      return createWikiImportJob({
        spaceId: treeQuery.space.id,
        parentId: null,
        files,
      });
    },
    onSuccess: async (job) => {
      if (!job) {
        return;
      }
      setImportJob(job);
      const items = await listWikiImportJobItems(job.id);
      setImportItems(items);
      const applied = await applyWikiImportJob(job.id);
      setImportJob(applied);
      const nextItems = await listWikiImportJobItems(job.id);
      setImportItems(nextItems);
      if (activeFeature) {
        await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(activeFeature.id) });
      }
      setBanner("Wiki 导入完成");
      setSelectedImportFiles([]);
    },
    onError: (error) => {
      setBanner(`导入失败：${messageFromError(error)}`);
    },
  });

  const imageAndLinkMaps = useMemo(() => {
    return buildWikiMarkdownLinkMaps(
      documentQuery.data?.resolved_refs_json ?? [],
      activeFeature?.id ?? null,
    );
  }, [activeFeature?.id, documentQuery.data?.resolved_refs_json]);

  const canEdit = Boolean(documentQuery.data?.permissions.write);
  const drawer = routeState.drawer;

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
    if (!activeFeature || !nodeDialog) {
      return;
    }
    try {
      if (nodeDialog.kind === "rename") {
        await renameNodeMutation.mutateAsync({
          nodeId: nodeDialog.node.id,
          name: value.trim(),
        });
        await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(activeFeature.id) });
        if (nodeDialog.node.type === "document") {
          await queryClient.invalidateQueries({
            queryKey: wikiQueryKeys.document(nodeDialog.node.id),
          });
        }
        setBanner("Wiki 节点已重命名");
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
      await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(activeFeature.id) });
      if (parentId != null) {
        setExpandedIds((current) => new Set(current).add(parentId));
      }
      setNodeDialog(null);
      if (!created) {
        return;
      }
      if (type === "document") {
        setBanner("已创建新的 Wiki 文档");
        onRouteChange({
          featureId: activeFeature.id,
          nodeId: created.id,
          mode: "edit",
          drawer: null,
        });
      } else {
        setBanner("已创建新的目录");
      }
    } catch (error) {
      setNodeDialogError(messageFromError(error));
    }
  }

  async function handleDeleteNode() {
    if (!activeFeature || nodeDialog?.kind !== "delete") {
      return;
    }
    try {
      await deleteNodeMutation.mutateAsync(nodeDialog.node.id);
      await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(activeFeature.id) });
      if (
        selectedNode &&
        (selectedNode.id === nodeDialog.node.id ||
          selectedNode.path.startsWith(`${nodeDialog.node.path}/`))
      ) {
        onRouteChange({ nodeId: null, mode: "view", drawer: null });
      }
      setNodeDialog(null);
      setBanner("Wiki 节点已删除");
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
      onRouteChange({ mode: "view" });
      setBanner("已丢弃当前草稿");
    } catch (error) {
      setBanner(`丢弃草稿失败：${messageFromError(error)}`);
    }
  }

  return (
    <section className="workspace wiki-workspace" data-list-collapsed={treeCollapsed}>
      <WikiTreePane
        activeFeature={activeFeature}
        canManageFeature={canManageFeature}
        collapsed={treeCollapsed}
        expandedIds={expandedIds}
        featureOptions={features}
        onCreateDocument={(parent) => openCreateDocumentDialog(parent)}
        onCreateFolder={openCreateFolderDialog}
        onDeleteNode={openDeleteDialog}
        onFeatureChange={(featureId) =>
          onRouteChange({ featureId, nodeId: null, mode: "view", drawer: null })
        }
        onImport={() => onRouteChange({ drawer: "import" })}
        onRenameNode={openRenameDialog}
        onSelectSearchHit={(hit) => {
          onRouteChange({ nodeId: hit.node_id, mode: "view", drawer: null });
        }}
        onSelectNode={(node: WikiTreeNodeRecord) => {
          if (node.type === "document" || node.type === "report_ref") {
            onRouteChange({ nodeId: node.id, mode: "view", drawer: null });
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
      <section className="detail-panel wiki-detail-panel">
        {banner ? <div className="action-banner">{banner}</div> : null}
        {documentQuery.data && routeState.mode === "view" ? (
          <>
            <div className="page-header compact wiki-page-header">
              <div>
                <h1>{documentQuery.data.title}</h1>
                <p>{selectedNode?.path}</p>
              </div>
              <WikiFloatingActions
                canEdit={canEdit}
                onCopyLink={async () => {
                  await copyTextToClipboard(window.location.href);
                  setBanner("已复制当前 Wiki 链接");
                }}
                onEdit={() => onRouteChange({ mode: "edit", drawer: null })}
                onOpenDetail={() => onRouteChange({ drawer: "detail" })}
                onOpenHistory={() => onRouteChange({ drawer: "history" })}
                onOpenImport={() => onRouteChange({ drawer: "import" })}
              />
            </div>
            <WikiReader
              content={documentQuery.data.current_body_markdown ?? ""}
              imageSrcMap={imageAndLinkMaps.imageSrcMap}
              linkHrefMap={imageAndLinkMaps.linkHrefMap}
            />
          </>
        ) : null}

        {documentQuery.data && routeState.mode === "edit" ? (
          <WikiEditor
            autosaveLabel={
              draftAutosave.autosaveStatus === "saving"
                ? "正在自动保存草稿..."
                : draftAutosave.autosaveStatus === "saved"
                  ? "草稿已自动保存"
                  : "编辑中 · 自动草稿已开启"
            }
            bodyMarkdown={editingBody}
            imageSrcMap={imageAndLinkMaps.imageSrcMap}
            linkHrefMap={imageAndLinkMaps.linkHrefMap}
            onCancel={async () => {
              if (
                selectedNode &&
                editingBody ===
                  (documentQuery.data.draft_body_markdown ??
                    documentQuery.data.current_body_markdown ??
                    "")
              ) {
                onRouteChange({ mode: "view" });
                return;
              }
              setLeaveDialogOpen(true);
            }}
            onOpenHistory={() => onRouteChange({ drawer: "history" })}
            onPublish={() => publishMutation.mutate()}
            onToggleTree={() => setTreeCollapsed((value) => !value)}
            publishing={publishMutation.isPending}
            setBodyMarkdown={setEditingBody}
            showTreeToggle={treeCollapsed}
            title={documentQuery.data.title}
          />
        ) : null}

        {reportQuery.data && routeState.mode === "view" ? (
          <WikiReportViewer
            onOpenFeaturePage={() => {
              if (activeFeature) {
                onOpenFeature(activeFeature.id);
              }
            }}
            report={reportQuery.data}
          />
        ) : null}

        {!documentQuery.data && !reportQuery.data && activeFeature ? (
          <WikiEmptyState
            canCreate={canManageFeature}
            description="当前特性还没有 Wiki 文档，或当前选择的节点不是文档。"
            onCreateDocument={
              canManageFeature ? () => openCreateDocumentDialog(knowledgeRoot) : undefined
            }
            onImport={canManageFeature ? () => onRouteChange({ drawer: "import" }) : undefined}
            title="开始建设这个特性的 Wiki"
          />
        ) : null}

        {!activeFeature && !featureQuery.isLoading ? (
          <WikiEmptyState
            canCreate={false}
            description="当前还没有可用特性，先创建特性后再进入 Wiki。"
            onCreateDocument={undefined}
            onImport={undefined}
            title="还没有可用特性"
          />
        ) : null}
      </section>

      <WikiDetailDrawer
        document={documentQuery.data ?? null}
        path={selectedNode?.path ?? null}
        onClose={() => onRouteChange({ drawer: null })}
        open={drawer === "detail"}
        updatedAt={selectedNode?.updated_at ?? null}
      />
      <WikiVersionDrawer
        currentVersionId={currentVersion?.id ?? documentQuery.data?.current_version_id ?? null}
        diff={versionDiff}
        loading={compareMutation.isPending}
        onClose={() => onRouteChange({ drawer: null })}
        onCompare={(fromVersionId, toVersionId) =>
          compareMutation.mutate({ fromVersionId, toVersionId })
        }
        onRollback={(versionId) => rollbackMutation.mutate(versionId)}
        open={drawer === "history"}
        versions={versionsQuery.data?.versions ?? []}
      />
      <WikiImportDialog
        importItems={importItems}
        importJob={importJob}
        onApply={() => {
          if (selectedImportFiles.length > 0) {
            createImportJobMutation.mutate(selectedImportFiles);
          }
        }}
        onClose={() => onRouteChange({ drawer: null })}
        onFilesSelected={(files) => {
          setSelectedImportFiles(files);
          importMutation.mutate(files);
        }}
        open={drawer === "import"}
        pending={importMutation.isPending || createImportJobMutation.isPending}
        preflight={importPreflight}
      />
      {nodeDialog?.kind === "create_document" ? (
        <WikiNodeInputDialog
          confirmLabel="创建 Wiki"
          errorMessage={nodeDialogError}
          initialValue=""
          isSubmitting={createNodeMutation.isPending}
          modeLabel="document"
          onCancel={() => setNodeDialog(null)}
          onSubmit={handleNodeDialogSubmit}
          parentPath={nodeDialog.parent?.path ?? knowledgeRoot?.path ?? null}
          title="新建 Wiki"
        />
      ) : null}
      {nodeDialog?.kind === "create_folder" ? (
        <WikiNodeInputDialog
          confirmLabel="创建目录"
          errorMessage={nodeDialogError}
          initialValue=""
          isSubmitting={createNodeMutation.isPending}
          modeLabel="folder"
          onCancel={() => setNodeDialog(null)}
          onSubmit={handleNodeDialogSubmit}
          parentPath={nodeDialog.parent.path}
          title="新建目录"
        />
      ) : null}
      {nodeDialog?.kind === "rename" ? (
        <WikiNodeInputDialog
          confirmLabel="保存名称"
          errorMessage={nodeDialogError}
          initialValue={nodeDialog.node.name}
          isSubmitting={renameNodeMutation.isPending}
          modeLabel="rename"
          onCancel={() => setNodeDialog(null)}
          onSubmit={handleNodeDialogSubmit}
          parentPath={nodeDialog.node.path}
          title="重命名节点"
        />
      ) : null}
      {nodeDialog?.kind === "delete" ? (
        <WikiNodeDeleteDialog
          errorMessage={nodeDialogError}
          isDeleting={deleteNodeMutation.isPending}
          nodeName={nodeDialog.node.name}
          onCancel={() => setNodeDialog(null)}
          onConfirm={handleDeleteNode}
          path={nodeDialog.node.path}
        />
      ) : null}
      {leaveDialogOpen ? (
        <WikiEditLeaveDialog
          isPublishing={publishMutation.isPending}
          onCancel={() => setLeaveDialogOpen(false)}
          onDiscard={discardDraftAndLeave}
          onLeaveWithDraft={() => {
            setLeaveDialogOpen(false);
            onRouteChange({ mode: "view" });
          }}
          onPublish={() => {
            setLeaveDialogOpen(false);
            publishMutation.mutate();
          }}
        />
      ) : null}
    </section>
  );
}
