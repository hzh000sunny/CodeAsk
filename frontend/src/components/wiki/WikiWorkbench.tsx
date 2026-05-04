import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listFeatures } from "../../lib/api";
import {
  applyWikiImportJob,
  createWikiImportJob,
  createWikiNode,
  deleteWikiDraft,
  getWikiDiff,
  listWikiImportJobItems,
  preflightWikiImport,
  publishWikiDocument,
  rollbackWikiVersion,
} from "../../lib/wiki/api";
import { buildWikiMarkdownLinkMaps } from "../../lib/wiki/markdown";
import { wikiQueryKeys } from "../../lib/wiki/query-keys";
import type { WikiDrawer, WikiRouteState } from "../../lib/wiki/routing";
import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import type {
  WikiDocumentDiffRead,
  WikiImportJobItemsRead,
  WikiImportJobRead,
  WikiImportPreflightRead,
} from "../../types/wiki";
import { messageFromError } from "../features/feature-utils";
import { WikiDetailDrawer } from "./WikiDetailDrawer";
import { WikiEditor } from "./WikiEditor";
import { WikiEmptyState } from "./WikiEmptyState";
import { WikiFloatingActions } from "./WikiFloatingActions";
import { WikiImportDialog } from "./WikiImportDialog";
import { WikiReader } from "./WikiReader";
import { WikiTreePane } from "./WikiTreePane";
import { WikiVersionDrawer } from "./WikiVersionDrawer";
import { useWikiDocument } from "./hooks/useWikiDocument";
import { useWikiDraftAutosave } from "./hooks/useWikiDraftAutosave";
import { useWikiTree } from "./hooks/useWikiTree";
import { copyTextToClipboard } from "../session/session-clipboard";

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
  const featureQuery = useQuery({
    queryKey: ["features"],
    queryFn: listFeatures,
  });
  const features = featureQuery.data ?? [];
  const activeFeature =
    features.find((feature) => feature.id === routeState.featureId) ?? features[0] ?? null;
  const treeQuery = useWikiTree(activeFeature?.id ?? null, routeState.nodeId);
  const selectedNode = treeQuery.selectedNode;
  const documentEnabled = selectedNode?.type === "document";
  const { currentVersion, documentQuery, versionsQuery } = useWikiDocument(
    selectedNode?.id ?? null,
    Boolean(documentEnabled),
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
    if (!treeQuery.tree.length || !activeFeature) {
      return;
    }
    if (routeState.nodeId != null && treeQuery.selectedNode) {
      return;
    }
    if (treeQuery.firstDocument) {
      onRouteChange({ featureId: activeFeature.id, nodeId: treeQuery.firstDocument.id });
      return;
    }
    onRouteChange({ featureId: activeFeature.id, nodeId: null });
  }, [
    activeFeature,
    onRouteChange,
    routeState.nodeId,
    treeQuery.firstDocument,
    treeQuery.selectedNode,
    treeQuery.tree,
  ]);

  useEffect(() => {
    const nextExpanded = new Set<number>();
    for (const root of treeQuery.tree) {
      if (root.system_role === "knowledge_base") {
        nextExpanded.add(root.id);
      }
    }
    setExpandedIds(nextExpanded);
  }, [activeFeature?.id, treeQuery.tree]);

  useEffect(() => {
    if (routeState.mode === "edit") {
      setTreeCollapsed(true);
    }
  }, [routeState.mode]);

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

  const createDocMutation = useMutation({
    mutationFn: async () => {
      if (!treeQuery.space) {
        return null;
      }
      const parentId = treeQuery.tree.find((node) => node.system_role === "knowledge_base")?.id ?? null;
      return createWikiNode({
        space_id: treeQuery.space.id,
        parent_id: parentId,
        type: "document",
        name: "New Wiki",
      });
    },
    onSuccess: (node) => {
      if (!node || !activeFeature) {
        return;
      }
      setBanner("已创建新的 Wiki 文档");
      void queryClient.invalidateQueries({ queryKey: wikiQueryKeys.tree(activeFeature.id) });
      onRouteChange({
        featureId: activeFeature.id,
        nodeId: node.id,
        mode: "edit",
        drawer: null,
      });
    },
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

  return (
    <section className="workspace wiki-workspace" data-list-collapsed={treeCollapsed}>
      <WikiTreePane
        activeFeature={activeFeature}
        collapsed={treeCollapsed}
        expandedIds={expandedIds}
        featureOptions={features}
        onCreateDocument={() => createDocMutation.mutate()}
        onFeatureChange={(featureId) =>
          onRouteChange({ featureId, nodeId: null, mode: "view", drawer: null })
        }
        onImport={() => onRouteChange({ drawer: "import" })}
        onSelectNode={(node: WikiTreeNodeRecord) => {
          if (node.type === "document") {
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
        roots={treeQuery.tree}
        search={search}
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
              if (selectedNode && editingBody === (documentQuery.data.draft_body_markdown ?? documentQuery.data.current_body_markdown ?? "")) {
                onRouteChange({ mode: "view" });
                return;
              }
              const decision = window.prompt("输入 keep 保留草稿退出，drop 丢弃草稿，publish 直接发布", "keep");
              if (decision === "drop" && selectedNode) {
                await deleteWikiDraft(selectedNode.id);
                draftAutosave.markSavedBaseline(documentQuery.data.current_body_markdown ?? "");
                setEditingBody(documentQuery.data.current_body_markdown ?? "");
                onRouteChange({ mode: "view" });
                return;
              }
              if (decision === "publish") {
                publishMutation.mutate();
                return;
              }
              onRouteChange({ mode: "view" });
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

        {!documentQuery.data && activeFeature ? (
          <WikiEmptyState
            canCreate
            description="当前特性还没有 Wiki 文档，或当前选择的节点不是文档。"
            onCreateDocument={() => createDocMutation.mutate()}
            onImport={() => onRouteChange({ drawer: "import" })}
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
    </section>
  );
}
