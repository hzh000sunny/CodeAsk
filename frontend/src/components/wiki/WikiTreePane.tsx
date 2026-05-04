import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";

import type { FeatureRead } from "../../types/api";
import type { WikiSearchHitRead } from "../../types/wiki";
import type { WikiSearchHitGroup } from "../../lib/wiki/presentation";
import { filterWikiTreeByQuery, type WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { WikiTreeNode } from "./WikiTreeNode";

export function WikiTreePane({
  activeFeature,
  canManageFeature,
  collapsed,
  expandedIds,
  featureOptions,
  onCreateDocument,
  onCreateFolder,
  onDeleteNode,
  onFeatureChange,
  onImport,
  onRenameNode,
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
  activeFeature: FeatureRead | null;
  canManageFeature: boolean;
  collapsed: boolean;
  expandedIds: Set<number>;
  featureOptions: FeatureRead[];
  onCreateDocument: (node?: WikiTreeNodeRecord | null) => void;
  onCreateFolder: (node: WikiTreeNodeRecord) => void;
  onDeleteNode: (node: WikiTreeNodeRecord) => void;
  onFeatureChange: (featureId: number) => void;
  onImport: () => void;
  onRenameNode: (node: WikiTreeNodeRecord) => void;
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
    <aside className="wiki-tree-pane" data-collapsed={collapsed}>
      <button
        aria-label={collapsed ? "展开 Wiki 目录" : "收起 Wiki 目录"}
        className="edge-collapse-button secondary"
        data-collapsed={collapsed}
        onClick={onToggleCollapsed}
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
            <label className="field-label compact">
              当前特性
              <select
                className="input wiki-select"
                onChange={(event) => onFeatureChange(Number(event.target.value))}
                value={activeFeature?.id ?? ""}
              >
                {featureOptions.map((feature) => (
                  <option key={feature.id} value={feature.id}>
                    {feature.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="list-toolbar wiki-toolbar-row">
              <label className="search-field">
                <Search aria-hidden="true" size={16} />
                <Input
                  aria-label="搜索 Wiki 目录"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="搜索目录"
                  value={search}
                />
              </label>
              {canManageFeature ? (
                <Button
                  aria-label="导入 Wiki"
                  className="icon-only"
                  icon={<Plus size={17} />}
                  onClick={onImport}
                  title="导入目录或文件"
                  type="button"
                />
              ) : null}
            </div>
            {canManageFeature ? (
              <Button
                icon={<Plus size={16} />}
                onClick={() => onCreateDocument()}
                type="button"
                variant="secondary"
              >
                新建 Wiki
              </Button>
            ) : null}
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
