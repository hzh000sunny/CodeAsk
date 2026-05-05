import { ChevronDown, ChevronRight, FileText, FolderOpen, FolderTree } from "lucide-react";

import { cn } from "../../lib/utils";
import type { WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { WikiNodeMenu } from "./WikiNodeMenu";

export function WikiTreeNode({
  canManage,
  depth,
  expandedIds,
  node,
  onCreateDocument,
  onCreateFolder,
  onDelete,
  onImport,
  onRename,
  onSelect,
  onToggle,
  selectedNodeId,
}: {
  canManage: boolean;
  depth: number;
  expandedIds: Set<number>;
  node: WikiTreeNodeRecord;
  onCreateDocument: (node: WikiTreeNodeRecord) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDelete: (node: WikiTreeNodeRecord) => void;
  onImport: (node: WikiTreeNodeRecord) => void;
  onRename: (node: WikiTreeNodeRecord) => void;
  onSelect: (node: WikiTreeNodeRecord) => void;
  onToggle: (nodeId: number) => void;
  selectedNodeId: number | null;
}) {
  const expanded = expandedIds.has(node.id);
  const selected = node.id === selectedNodeId;
  const isFolder = node.type === "folder";
  const canExpand = isFolder && node.children.length > 0;

  return (
    <li className="wiki-tree-item">
      <div className="wiki-tree-row">
        <button
          className="wiki-tree-button"
          data-selected={selected}
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
            {canExpand ? (
              expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
            ) : (
              <span />
            )}
          </span>
          <span className="wiki-tree-icon">
            {isFolder ? (
              expanded ? <FolderOpen size={15} /> : <FolderTree size={15} />
            ) : (
              <FileText size={15} />
            )}
          </span>
          <span className="wiki-tree-label">{node.name}</span>
        </button>
        <WikiNodeMenu
          canManage={canManage}
          node={node}
          onCreateDocument={onCreateDocument}
          onCreateFolder={onCreateFolder}
          onDelete={onDelete}
          onImport={onImport}
          onRename={onRename}
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
              onImport={onImport}
              onRename={onRename}
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
