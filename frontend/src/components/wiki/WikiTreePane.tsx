import type { KeyboardEvent as ReactKeyboardEvent, MouseEvent as ReactMouseEvent } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";

import type { WikiSearchHitRead } from "../../types/wiki";
import {
  formatWikiSearchHitHeading,
  type WikiSearchHitGroup,
} from "../../lib/wiki/presentation";
import { filterWikiTreeByQuery, type WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { Input } from "../ui/input";
import { WikiTreeNode } from "./WikiTreeNode";

export function WikiTreePane({
  canManageFeature,
  collapsed,
  expandedIds,
  onCreateDocument,
  onCreateFolder,
  onDeleteNode,
  onImport,
  onImportNode,
  onRenameNode,
  onResizeFromCollapseButton,
  onSelectSearchHit,
  onSelectNode,
  onToggleCollapsed,
  onToggleNode,
  roots,
  search,
  searchGroups,
  searchLoading,
  selectedNodeId,
  setSearch,
}: {
  canManageFeature: boolean;
  collapsed: boolean;
  expandedIds: Set<number>;
  onCreateDocument: (node?: WikiTreeNodeRecord | null) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDeleteNode: (node: WikiTreeNodeRecord) => void;
  onImport: () => void;
  onImportNode: (node: WikiTreeNodeRecord) => void;
  onRenameNode: (node: WikiTreeNodeRecord) => void;
  onResizeFromCollapseButton: (event: ReactMouseEvent<HTMLButtonElement>) => void;
  onSelectSearchHit: (hit: WikiSearchHitRead) => void;
  onSelectNode: (node: WikiTreeNodeRecord) => void;
  onToggleCollapsed: () => void;
  onToggleNode: (nodeId: number) => void;
  roots: WikiTreeNodeRecord[];
  search: string;
  searchGroups: WikiSearchHitGroup[];
  searchLoading: boolean;
  selectedNodeId: number | null;
  setSearch: (value: string) => void;
}) {
  const visibleRoots = filterWikiTreeByQuery(roots, search);
  const showSearchResults = search.trim().length > 0;

  return (
    <aside
      aria-label="Wiki 目录树"
      className="wiki-tree-pane"
      data-collapsed={collapsed}
    >
      <button
        aria-label={collapsed ? "展开 Wiki 目录" : "收起 Wiki 目录"}
        className="edge-collapse-button secondary wiki-tree-collapse-button"
        data-collapsed={collapsed}
        onKeyDown={(event: ReactKeyboardEvent<HTMLButtonElement>) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onToggleCollapsed();
          }
        }}
        onMouseDown={onResizeFromCollapseButton}
        title={collapsed ? "展开 Wiki 目录" : "收起 Wiki 目录"}
        type="button"
      >
        {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
      </button>
      {collapsed ? (
        <div className="collapsed-panel-label">Wiki</div>
      ) : (
        <>
          <div className="wiki-tree-toolbar">
            <div className="list-toolbar wiki-toolbar-row">
              <label className="search-field">
                <Search aria-hidden="true" size={16} />
                <Input
                  aria-label="搜索 Wiki 目录"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索"
                  value={search}
                />
              </label>
            </div>
          </div>
          <div className="list-scroll wiki-tree-scroll">
            {showSearchResults ? (
              <div className="wiki-search-results">
                {searchLoading ? (
                  <div className="empty-block">
                    <p>正在搜索 Wiki</p>
                    <span>正在整理当前特性的文档和问题报告。</span>
                  </div>
                ) : searchGroups.length === 0 ? (
                  <div className="empty-block">
                    <p>没有匹配结果</p>
                    <span>尝试缩短关键词，或切换到其它特性。</span>
                  </div>
                ) : (
                  searchGroups.map((group) => (
                    <section className="wiki-search-group" key={group.key}>
                      <div className="wiki-search-group-title">{group.label}</div>
                      <div className="wiki-search-group-items">
                        {group.items.map((item) => (
                          <button
                            className="wiki-search-hit"
                            key={`${item.kind}-${item.node_id}`}
                            onClick={() => onSelectSearchHit(item)}
                            type="button"
                          >
                            <strong>{item.title}</strong>
                            <span>{item.path}</span>
                            {formatWikiSearchHitHeading(item) ? (
                              <em>{formatWikiSearchHitHeading(item)}</em>
                            ) : null}
                            <small>{item.snippet}</small>
                          </button>
                        ))}
                      </div>
                    </section>
                  ))
                )}
              </div>
            ) : visibleRoots.length === 0 ? (
              <div className="empty-block">
                <p>没有可显示的节点</p>
                <span>尝试切换特性或清空搜索条件。</span>
              </div>
            ) : (
              <ul className="wiki-tree-list">
                {visibleRoots.map((node) => (
                  <WikiTreeNode
                    canManage={canManageFeature}
                    depth={0}
                    expandedIds={expandedIds}
                    key={node.id}
                    node={node}
                    onCreateDocument={(targetNode) => onCreateDocument(targetNode)}
                    onCreateFolder={onCreateFolder}
                    onDelete={onDeleteNode}
                    onImport={onImportNode}
                    onRename={onRenameNode}
                    onSelect={onSelectNode}
                    onToggle={onToggleNode}
                    selectedNodeId={selectedNodeId}
                  />
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
