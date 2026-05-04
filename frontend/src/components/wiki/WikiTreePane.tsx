import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";

import type { FeatureRead } from "../../types/api";
import { filterWikiTreeByQuery, type WikiTreeNodeRecord } from "../../lib/wiki/tree";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { WikiTreeNode } from "./WikiTreeNode";

export function WikiTreePane({
  activeFeature,
  collapsed,
  expandedIds,
  featureOptions,
  onCreateDocument,
  onFeatureChange,
  onImport,
  onSelectNode,
  onToggleCollapsed,
  onToggleNode,
  roots,
  search,
  selectedNodeId,
  setSearch,
}: {
  activeFeature: FeatureRead | null;
  collapsed: boolean;
  expandedIds: Set<number>;
  featureOptions: FeatureRead[];
  onCreateDocument: () => void;
  onFeatureChange: (featureId: number) => void;
  onImport: () => void;
  onSelectNode: (node: WikiTreeNodeRecord) => void;
  onToggleCollapsed: () => void;
  onToggleNode: (nodeId: number) => void;
  roots: WikiTreeNodeRecord[];
  search: string;
  selectedNodeId: number | null;
  setSearch: (value: string) => void;
}) {
  const visibleRoots = filterWikiTreeByQuery(roots, search);

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
              <Button
                aria-label="导入 Wiki"
                className="icon-only"
                icon={<Plus size={17} />}
                onClick={onImport}
                title="导入目录或文件"
                type="button"
              />
            </div>
            <Button
              icon={<Plus size={16} />}
              onClick={onCreateDocument}
              type="button"
              variant="secondary"
            >
              新建 Wiki
            </Button>
          </div>
          <div className="list-scroll wiki-tree-scroll">
            {visibleRoots.length === 0 ? (
              <div className="empty-block">
                <p>没有可显示的节点</p>
                <span>尝试切换特性或清空搜索条件。</span>
              </div>
            ) : (
              <ul className="wiki-tree-list">
                {visibleRoots.map((node) => (
                  <WikiTreeNode
                    depth={0}
                    expandedIds={expandedIds}
                    key={node.id}
                    node={node}
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
