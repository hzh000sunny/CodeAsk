import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpenText,
  ChevronDown,
  ChevronRight,
  FolderTree,
} from "lucide-react";

import {
  getWikiDocument,
  getWikiReportByNode,
  getWikiTree,
  listWikiReportProjections,
} from "../../lib/wiki/api";
import { buildWikiMarkdownLinkMaps } from "../../lib/wiki/markdown";
import { injectWikiReportProjections } from "../../lib/wiki/presentation";
import {
  buildWikiTree,
  findFirstReadableDocument,
  findNodeById,
  type WikiTreeNodeRecord,
} from "../../lib/wiki/tree";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { Button } from "../ui/button";

export function KnowledgePanel({
  featureId,
  onOpenWiki,
}: {
  featureId?: number;
  onOpenWiki: (featureId: number, options?: { drawer?: "import" | null; nodeId?: number | null }) => void;
}) {
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const treeQuery = useQuery({
    queryKey: ["feature-knowledge-preview", featureId],
    queryFn: () => getWikiTree(featureId as number),
    enabled: Boolean(featureId),
  });
  const reportsQuery = useQuery({
    queryKey: ["feature-knowledge-reports", featureId],
    queryFn: () => listWikiReportProjections(featureId as number),
    enabled: Boolean(featureId),
  });

  const baseTree = useMemo(
    () => buildWikiTree(treeQuery.data?.nodes ?? []),
    [treeQuery.data?.nodes],
  );
  const tree = useMemo(
    () => injectWikiReportProjections(baseTree, reportsQuery.data?.items ?? []),
    [baseTree, reportsQuery.data?.items],
  );
  const selectedNode = useMemo(
    () => findNodeById(tree, selectedNodeId),
    [selectedNodeId, tree],
  );
  const firstDocument = useMemo(() => findFirstReadableDocument(tree), [tree]);

  useEffect(() => {
    if (selectedNodeId != null && selectedNode) {
      return;
    }
    setSelectedNodeId(firstDocument?.id ?? null);
  }, [firstDocument?.id, selectedNode, selectedNodeId]);

  useEffect(() => {
    if (tree.length === 0) {
      setExpandedIds(new Set());
      return;
    }
    const knowledgeRoot = tree.find((node) => node.system_role === "knowledge_base") ?? tree[0];
    setExpandedIds(knowledgeRoot ? new Set([knowledgeRoot.id]) : new Set());
  }, [tree]);

  const documentQuery = useQuery({
    queryKey: ["feature-knowledge-document", selectedNode?.id],
    queryFn: () => getWikiDocument(selectedNode?.id as number),
    enabled: selectedNode?.type === "document",
  });
  const reportQuery = useQuery({
    queryKey: ["feature-knowledge-report", selectedNode?.id],
    queryFn: () => getWikiReportByNode(selectedNode?.id as number),
    enabled: selectedNode?.type === "report_ref",
  });

  const previewTitle =
    documentQuery.data?.title ?? reportQuery.data?.title ?? selectedNode?.name ?? "预览";
  const previewBody =
    documentQuery.data?.current_body_markdown ?? reportQuery.data?.body_markdown ?? "";
  const previewRefMaps = useMemo(
    () =>
      buildWikiMarkdownLinkMaps(
        documentQuery.data?.resolved_refs_json ?? [],
        featureId ?? null,
      ),
    [documentQuery.data?.resolved_refs_json, featureId],
  );
  const brokenImageTargets = useMemo(
    () =>
      new Set(
        (documentQuery.data?.broken_refs_json?.assets ?? []).map((item) => item.target),
      ),
    [documentQuery.data?.broken_refs_json?.assets],
  );

  return (
    <div className="tab-content two-column knowledge-tab-content">
      <section className="surface knowledge-tree-surface">
        <div className="content-toolbar">
          <div className="section-title">
            <FolderTree aria-hidden="true" size={18} />
            <h2>Wiki 目录</h2>
          </div>
          {featureId ? (
            <div className="header-actions">
              <Button
                onClick={() => onOpenWiki(featureId, { nodeId: selectedNodeId })}
                type="button"
                variant="secondary"
              >
                进入 Wiki 工作台
              </Button>
            </div>
          ) : null}
        </div>
        {!featureId ? (
          <div className="empty-block wide">
            <p>先选择一个特性，再查看该特性的 Wiki 目录。</p>
          </div>
        ) : treeQuery.isLoading ? (
          <div className="empty-block wide">
            <p>正在加载 Wiki 目录。</p>
          </div>
        ) : tree.length === 0 ? (
          <div className="empty-block wide">
            <p>当前特性还没有 Wiki 内容。</p>
          </div>
        ) : (
          <div className="knowledge-tree-scroll">
            <ul className="knowledge-tree-list">
              {tree.map((node) => (
                <KnowledgeTreePreviewNode
                  depth={0}
                  expandedIds={expandedIds}
                  key={node.id}
                  node={node}
                  onSelect={setSelectedNodeId}
                  onToggle={(nodeId) =>
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
                  selectedNodeId={selectedNodeId}
                />
              ))}
            </ul>
          </div>
        )}
      </section>
      <section className="surface knowledge-preview-surface">
        <div className="content-toolbar">
          <div className="section-title">
            <BookOpenText aria-hidden="true" size={18} />
            <h2>内容预览</h2>
          </div>
        </div>
        {!featureId ? (
          <div className="empty-block wide">
            <p>当前没有可预览的特性。</p>
          </div>
        ) : !selectedNode ? (
          <div className="empty-block wide">
            <p>当前特性还没有可预览的 Wiki 文档。</p>
          </div>
        ) : documentQuery.isLoading || reportQuery.isLoading ? (
          <div className="empty-block wide">
            <p>正在加载预览内容。</p>
          </div>
        ) : (
          <article className="report-preview knowledge-preview">
            <MarkdownRenderer
              brokenImageTargets={brokenImageTargets}
              content={previewBody}
              imageSrcMap={previewRefMaps.imageSrcMap}
              linkHrefMap={previewRefMaps.linkHrefMap}
            />
          </article>
        )}
      </section>
    </div>
  );
}

function KnowledgeTreePreviewNode({
  depth,
  expandedIds,
  node,
  onSelect,
  onToggle,
  selectedNodeId,
}: {
  depth: number;
  expandedIds: Set<number>;
  node: WikiTreeNodeRecord;
  onSelect: (nodeId: number) => void;
  onToggle: (nodeId: number) => void;
  selectedNodeId: number | null;
}) {
  const isSelectable = node.type === "document" || node.type === "report_ref";
  const isFolder = node.type === "folder";
  const expanded = expandedIds.has(node.id);
  const selected = node.id === selectedNodeId;

  return (
    <li className="knowledge-tree-item">
      <button
        aria-expanded={isFolder ? expanded : undefined}
        className="knowledge-tree-button"
        data-selected={selected}
        onClick={() => {
          if (isFolder) {
            onToggle(node.id);
            return;
          }
          if (isSelectable) {
            onSelect(node.id);
          }
        }}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
        type="button"
      >
        <span className="knowledge-tree-prefix" aria-hidden="true">
          {isFolder ? (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : null}
        </span>
        <span className="knowledge-tree-name">{node.name}</span>
        {node.type === "report_ref" ? <small>问题报告</small> : null}
      </button>
      {node.children.length > 0 && expanded ? (
        <ul className="knowledge-tree-list">
          {node.children.map((child) => (
            <KnowledgeTreePreviewNode
              depth={depth + 1}
              expandedIds={expandedIds}
              key={child.id}
              node={child}
              onSelect={onSelect}
              onToggle={onToggle}
              selectedNodeId={selectedNodeId}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
