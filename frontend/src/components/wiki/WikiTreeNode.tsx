import type { DragEvent as ReactDragEvent } from "react";
import {
  Archive,
  Boxes,
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  History,
  Layers,
  Library,
  Microscope,
  ScrollText,
  type LucideIcon,
} from "lucide-react";

import { cn } from "../../lib/utils";
import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { canMoveWikiNode, getNodeMoveFlags } from "../../lib/wiki/tree-ordering";
import { WikiNodeMenu } from "./WikiNodeMenu";
import { WikiTreeDropIndicator } from "./WikiTreeDropIndicator";

// 按节点角色挑选类型图标：用形状区分角色，颜色统一保持静音灰（ink-and-paper）。
// 特殊系统角色优先（知识库 / 特性·当前 / 特性·历史 / 分组 / 报告集合），
// 其余落到通用的 文件夹（开合）/ 报告引用 / 文档。
function resolveNodeTypeIcon(node: WikiTreeNodeRecord, expanded: boolean): LucideIcon {
  switch (node.system_role) {
    case "knowledge_base":
      return Library;
    case "feature_space_current":
      return Boxes;
    case "feature_space_history":
      return History;
    case "feature_group_current":
      return Layers;
    case "feature_group_history":
      return Archive;
    case "reports":
      // 问题定位报告（顶层容器，与知识库同级）——研究/排查身份，区别于文档。
      return Microscope;
    default:
      // report_group（草稿/已验证/未通过）落到下面的文件夹分支——它们本就是目录。
      break;
  }
  if (node.type === "report_ref") {
    // 单篇报告：卷轴形，和普通文档（FileText）形状拉开。
    return ScrollText;
  }
  if (node.type === "folder") {
    return expanded ? FolderOpen : Folder;
  }
  return FileText;
}

export function WikiTreeNode({
  activeFeatureNodeId = null,
  canManage,
  canRestoreArchivedSpace = false,
  expandedIds,
  node,
  onCreateDocument,
  onCreateFolder,
  onDelete,
  onDragEnd,
  onDragOverNode,
  onDragStart,
  onDropOnNode,
  onImport,
  onMoveDown,
  onMoveTarget,
  onMoveUp,
  onReindex,
  onRename,
  onRestoreArchivedSpace,
  onSelect,
  onToggle,
  selectedNodeId,
  treeRoots,
  withinHistoryFeature = false,
}: {
  activeFeatureNodeId?: number | null;
  canManage: boolean;
  canRestoreArchivedSpace?: boolean;
  expandedIds: Set<number>;
  node: WikiTreeNodeRecord;
  onCreateDocument: (node: WikiTreeNodeRecord) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDelete: (node: WikiTreeNodeRecord) => void;
  onDragEnd?: () => void;
  onDragOverNode?: (
    targetNode: WikiTreeNodeRecord,
    position: "before" | "inside" | "after",
    event: ReactDragEvent<HTMLElement>,
  ) => void;
  onDragStart?: (node: WikiTreeNodeRecord) => void;
  onDropOnNode?: (
    targetNode: WikiTreeNodeRecord,
    position: "before" | "inside" | "after",
    event: ReactDragEvent<HTMLElement>,
  ) => void;
  onImport: (node: WikiTreeNodeRecord) => void;
  onMoveDown?: (node: WikiTreeNodeRecord) => void;
  onMoveTarget?: { nodeId: number; position: "before" | "inside" | "after" } | null;
  onMoveUp?: (node: WikiTreeNodeRecord) => void;
  onReindex?: (node: WikiTreeNodeRecord) => void;
  onRename: (node: WikiTreeNodeRecord) => void;
  onRestoreArchivedSpace?: (node: WikiTreeNodeRecord) => void;
  onSelect: (node: WikiTreeNodeRecord) => void;
  onToggle: (nodeId: number) => void;
  selectedNodeId: number | null;
  treeRoots?: WikiTreeNodeRecord[];
  withinHistoryFeature?: boolean;
}) {
  // 历史特性是只读存档：其子树内不提供「新建/导入」入口（恢复/重新索引/重命名/删除照旧）。
  const nodeWithinHistoryFeature =
    withinHistoryFeature || node.system_role === "feature_space_history";
  const expanded = expandedIds.has(node.id);
  const selected = node.id === selectedNodeId;
  // 当前活动特性（未选中具体文档时）：在树里给特性根一个有别于文档选中的高亮，
  // 避免和「打开某文档」的选中态混淆，也保证同一时刻最多一个高亮。
  const activeFeature = !selected && activeFeatureNodeId != null && node.id === activeFeatureNodeId;
  const isFolder = node.type === "folder";
  const canExpand = isFolder && node.children.length > 0;
  const TypeIcon = resolveNodeTypeIcon(node, expanded);
  const moveFlags = getNodeMoveFlags(treeRoots ?? [node], node.id);
  const canDrag = canMoveWikiNode(node);
  const beforeActive = onMoveTarget?.nodeId === node.id && onMoveTarget.position === "before";
  const insideActive = onMoveTarget?.nodeId === node.id && onMoveTarget.position === "inside";
  const afterActive = onMoveTarget?.nodeId === node.id && onMoveTarget.position === "after";

  return (
    <li className="wiki-tree-item">
      <WikiTreeDropIndicator
        active={beforeActive}
        nodeId={node.id}
        onDragOver={(event) => onDragOverNode?.(node, "before", event)}
        onDrop={(event) => onDropOnNode?.(node, "before", event)}
        position="before"
      />
      <div className="wiki-tree-row">
        <button
          className="wiki-tree-button"
          data-selected={selected}
          data-active-feature={activeFeature || undefined}
          data-drop-active={insideActive}
          data-drop-zone={isFolder ? "inside" : undefined}
          data-node-id={isFolder ? node.id : undefined}
          draggable={canDrag}
          onDragEnd={() => onDragEnd?.()}
          onDragOver={(event) => {
            if (isFolder) {
              onDragOverNode?.(node, "inside", event);
            }
          }}
          onDragStart={() => onDragStart?.(node)}
          onDrop={(event) => {
            if (isFolder) {
              onDropOnNode?.(node, "inside", event);
            }
          }}
          onClick={() => {
            if (isFolder) {
              onSelect(node);
              onToggle(node.id);
            } else {
              onSelect(node);
            }
          }}
          title={node.name}
          type="button"
        >
          <span
            className={cn("wiki-tree-caret", !canExpand && "is-placeholder")}
            data-expanded={canExpand && expanded ? "true" : undefined}
            onClick={(event) => {
              event.stopPropagation();
              if (canExpand) {
                onToggle(node.id);
              }
            }}
            role="presentation"
          >
            {canExpand ? <ChevronRight size={14} /> : null}
          </span>
          <span className="wiki-tree-icon">
            <TypeIcon size={15} />
          </span>
          <span className="wiki-tree-label">{node.name}</span>
        </button>
        <WikiNodeMenu
          canManage={canManage}
          canCreateContent={!nodeWithinHistoryFeature}
          canRestoreArchivedSpace={canRestoreArchivedSpace}
          canMoveDown={moveFlags.canMoveDown}
          canMoveUp={moveFlags.canMoveUp}
          node={node}
          onCreateDocument={onCreateDocument}
          onCreateFolder={onCreateFolder}
          onDelete={onDelete}
          onImport={onImport}
          onMoveDown={onMoveDown}
          onMoveUp={onMoveUp}
          onReindex={onReindex}
          onRename={onRename}
          onRestoreArchivedSpace={onRestoreArchivedSpace}
        />
      </div>
      {canExpand && expanded ? (
        <ul className="wiki-tree-children">
          {node.children.map((child) => (
            <WikiTreeNode
              activeFeatureNodeId={activeFeatureNodeId}
              canManage={canManage}
              expandedIds={expandedIds}
              key={child.id}
              node={child}
              onCreateDocument={onCreateDocument}
              onCreateFolder={onCreateFolder}
              onDelete={onDelete}
              onDragEnd={onDragEnd}
              onDragOverNode={onDragOverNode}
              onDragStart={onDragStart}
              onDropOnNode={onDropOnNode}
              onImport={onImport}
              onMoveDown={onMoveDown}
              onMoveTarget={onMoveTarget}
              onMoveUp={onMoveUp}
              onReindex={onReindex}
              onRename={onRename}
              onRestoreArchivedSpace={onRestoreArchivedSpace}
              onSelect={onSelect}
              onToggle={onToggle}
              selectedNodeId={selectedNodeId}
              treeRoots={treeRoots ?? [node]}
              canRestoreArchivedSpace={canRestoreArchivedSpace}
              withinHistoryFeature={nodeWithinHistoryFeature}
            />
          ))}
        </ul>
      ) : null}
      <WikiTreeDropIndicator
        active={afterActive}
        nodeId={node.id}
        onDragOver={(event) => onDragOverNode?.(node, "after", event)}
        onDrop={(event) => onDropOnNode?.(node, "after", event)}
        position="after"
      />
    </li>
  );
}
