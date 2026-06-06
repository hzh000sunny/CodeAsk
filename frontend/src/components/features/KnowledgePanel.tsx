import {
  createElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpenText, ChevronRight, FolderTree, PanelsTopLeft } from "lucide-react";

import {
  getWikiDocument,
  getWikiReportByNode,
  getWikiTree,
  listWikiReportProjections,
} from "../../lib/wiki/api";
import { buildWikiMarkdownLinkMaps } from "../../lib/wiki/markdown";
import { injectWikiReportProjections } from "../../lib/wiki/presentation";
import {
  buildWikiNodeDisplayPath,
  buildWikiTree,
  findFirstReadableDocument,
  findNodeById,
  type WikiTreeNodeRecord,
} from "../../lib/wiki/tree";
import { cn } from "../../lib/utils";
import { MarkdownRenderer } from "../ui/MarkdownRenderer";
import { Button } from "../ui/button";
import { resolveNodeTypeIcon } from "../wiki/WikiTreeNode";

export function KnowledgePanel({
  featureId,
  featureName,
  onOpenWiki,
}: {
  featureId?: number;
  featureName?: string | null;
  onOpenWiki: (featureId: number, options?: { drawer?: "import" | null; nodeId?: number | null }) => void;
}) {
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // 目录树 / 预览之间的左右拖动条：与 Wiki 编辑页的 split 拖柄同款，
  // 但树用受控的像素宽（而非 fr 比例），保证预览始终留出阅读宽度。
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [treeWidth, setTreeWidth] = useState(340);
  const MIN_TREE = 220;
  const MAX_TREE = 520;
  const KEY_STEP = 24;

  function startDrag(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    const grid = gridRef.current;
    if (!grid) {
      return;
    }
    const rect = grid.getBoundingClientRect();
    // 树列从内容盒左沿起算，需扣掉 .tab-content 的左内边距，拖柄才贴着光标。
    const padLeft = Number.parseFloat(getComputedStyle(grid).paddingLeft) || 0;
    const onMove = (move: PointerEvent) => {
      // 预览至少留 360px，避免把正文重新压窄。
      const max = Math.min(MAX_TREE, rect.width - padLeft - 360);
      setTreeWidth(Math.min(max, Math.max(MIN_TREE, move.clientX - rect.left - padLeft)));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.style.cursor = "";
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    document.body.style.cursor = "col-resize";
  }

  function onDividerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setTreeWidth((value) => Math.max(MIN_TREE, value - KEY_STEP));
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setTreeWidth((value) => Math.min(MAX_TREE, value + KEY_STEP));
    } else if (event.key === "Home") {
      event.preventDefault();
      setTreeWidth(340);
    }
  }

  const gridStyle = { "--kn-tree": `${treeWidth}px` } as CSSProperties;

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

  // 预览报头的全路径：从特性开始，例如「支付结算 / 知识库 / 接入 / 支付接入说明」。
  // buildWikiNodeDisplayPath 给出特性内部的路径（知识库/… /当前节点），再补上特性名。
  const previewPath = useMemo(() => {
    if (selectedNode == null) {
      return null;
    }
    const innerPath = buildWikiNodeDisplayPath(tree, selectedNode.id);
    return [featureName?.trim(), innerPath].filter(Boolean).join(" / ");
  }, [featureName, selectedNode, tree]);

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
    <div
      className="tab-content two-column knowledge-tab-content"
      ref={gridRef}
      style={gridStyle}
    >
      <section className="surface knowledge-tree-surface">
        <div className="content-toolbar knowledge-tree-toolbar-row">
          <div className="section-title">
            <FolderTree aria-hidden="true" size={18} />
            <h2>Wiki 目录</h2>
          </div>
          {featureId ? (
            <div className="header-actions">
              <Button
                icon={<PanelsTopLeft size={15} />}
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
            <ul className="wiki-tree-list">
              {tree.map((node) => (
                <KnowledgeTreePreviewNode
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
      <button
        aria-label="拖动调整目录树与预览的宽度"
        aria-orientation="vertical"
        className="wiki-split-divider"
        onKeyDown={onDividerKeyDown}
        onPointerDown={startDrag}
        role="separator"
        tabIndex={0}
        type="button"
      />
      <section className="surface knowledge-preview-surface">
        <div className="content-toolbar">
          <div className="section-title knowledge-preview-heading">
            <BookOpenText aria-hidden="true" size={18} />
            <h2>内容预览</h2>
            {previewPath ? (
              <span className="knowledge-preview-name" title={previewPath}>
                {previewPath}
              </span>
            ) : null}
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

// 复用 Wiki 工作台的树视觉（caret + 角色图标 + 缩进连接线 + 静音选中态），
// 但去掉拖拽/节点菜单等编辑能力——这里是只读预览树。
function KnowledgeTreePreviewNode({
  expandedIds,
  node,
  onSelect,
  onToggle,
  selectedNodeId,
}: {
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
  const canExpand = node.children.length > 0;
  // 角色图标按节点动态选取；用 createElement 而非 <Icon/>，避免在 render 中即时
  // 创建组件（react-hooks/static-components）。
  const typeIcon = createElement(resolveNodeTypeIcon(node, expanded), { size: 15 });

  return (
    <li className="wiki-tree-item">
      <div className="wiki-tree-row">
        <button
          aria-expanded={canExpand ? expanded : undefined}
          className="wiki-tree-button"
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
          title={node.name}
          type="button"
        >
          <span
            className={cn("wiki-tree-caret", !canExpand && "is-placeholder")}
            data-expanded={canExpand && expanded ? "true" : undefined}
            onClick={(event) => {
              if (!canExpand) {
                return;
              }
              event.stopPropagation();
              onToggle(node.id);
            }}
            role="presentation"
          >
            {canExpand ? <ChevronRight size={14} /> : null}
          </span>
          <span className="wiki-tree-icon">{typeIcon}</span>
          <span className="wiki-tree-label">{node.name}</span>
        </button>
      </div>
      {canExpand && expanded ? (
        <ul className="wiki-tree-children">
          {node.children.map((child) => (
            <KnowledgeTreePreviewNode
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
