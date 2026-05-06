import type { DragEvent as ReactDragEvent } from "react";
import { Component, FileText, FolderOpen } from "lucide-react";

import { cn } from "../../lib/utils";
import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { canMoveWikiNode, getNodeMoveFlags } from "../../lib/wiki/tree-ordering";
import { WikiNodeMenu } from "./WikiNodeMenu";
import { WikiTreeDropIndicator } from "./WikiTreeDropIndicator";

export function WikiTreeNode({
  canManage,
  canRestoreArchivedSpace = false,
  depth,
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
}: {
  canManage: boolean;
  canRestoreArchivedSpace?: boolean;
  depth: number;
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
}) {
  const expanded = expandedIds.has(node.id);
  const selected = node.id === selectedNodeId;
  const isFolder = node.type === "folder";
  const isFeatureRoot =
    node.system_role === "feature_space_current" || node.system_role === "feature_space_history";
  const canExpand = isFolder && node.children.length > 0;
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
          style={{ paddingLeft: `${12 + depth * 16}px` }}
          title={node.name}
          type="button"
        >
          <span
            className={cn("wiki-tree-chevron", !canExpand && "is-placeholder")}
            onClick={(event) => {
              event.stopPropagation();
              if (canExpand) {
                onToggle(node.id);
              }
            }}
            role="presentation"
          >
            {isFolder ? (isFeatureRoot ? <Component size={14} /> : <FolderOpen size={14} />) : <span />}
          </span>
          <span className="wiki-tree-icon">
            {isFolder ? null : <FileText size={15} />}
          </span>
          <span className="wiki-tree-label">{node.name}</span>
        </button>
        <WikiNodeMenu
          canManage={canManage}
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
              canManage={canManage}
              depth={depth + 1}
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
