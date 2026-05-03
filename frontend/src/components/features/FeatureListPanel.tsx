import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";

import type { FeatureRead } from "../../types/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { FeatureListItem } from "./FeatureListItem";

export function FeatureListPanel({
  createPending,
  featureDescription,
  featureName,
  isLoading,
  listCollapsed,
  onCreateSubmit,
  onDelete,
  onFeatureDescriptionChange,
  onFeatureNameChange,
  onQueryChange,
  onSelect,
  onShowCreateChange,
  onToggleCollapsed,
  pendingDelete,
  query,
  selectedFeatureId,
  showCreate,
  visibleFeatures,
}: {
  createPending: boolean;
  featureDescription: string;
  featureName: string;
  isLoading: boolean;
  listCollapsed: boolean;
  onCreateSubmit: () => void;
  onDelete: (feature: FeatureRead) => void;
  onFeatureDescriptionChange: (value: string) => void;
  onFeatureNameChange: (value: string) => void;
  onQueryChange: (value: string) => void;
  onSelect: (featureId: number) => void;
  onShowCreateChange: (value: boolean) => void;
  onToggleCollapsed: () => void;
  pendingDelete: boolean;
  query: string;
  selectedFeatureId: number | null;
  showCreate: boolean;
  visibleFeatures: FeatureRead[];
}) {
  return (
    <aside
      className="list-panel"
      data-collapsed={listCollapsed}
      role="region"
      aria-label="特性列表"
    >
      <button
        aria-label={listCollapsed ? "展开特性列表" : "收起特性列表"}
        className="edge-collapse-button secondary"
        data-collapsed={listCollapsed}
        onClick={onToggleCollapsed}
        title={listCollapsed ? "展开特性列表" : "收起特性列表"}
        type="button"
      >
        {listCollapsed ? (
          <ChevronRight aria-hidden="true" size={15} />
        ) : (
          <ChevronLeft aria-hidden="true" size={15} />
        )}
      </button>
      {listCollapsed ? (
        <div className="collapsed-panel-label">特性</div>
      ) : (
        <>
          <div className="list-toolbar">
            <label className="search-field">
              <Search aria-hidden="true" size={16} />
              <Input
                aria-label="搜索特性"
                onChange={(event) => onQueryChange(event.target.value)}
                placeholder="搜索特性"
                value={query}
              />
            </label>
            <Button
              aria-label="添加特性"
              className="icon-only"
              icon={<Plus size={17} />}
              onClick={() => onShowCreateChange(!showCreate)}
              title="添加特性"
              type="button"
            />
          </div>
          <div className="list-scroll">
            {showCreate ? (
              <form
                className="inline-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  onCreateSubmit();
                }}
              >
                <label className="field-label compact">
                  特性名称
                  <Input
                    onChange={(event) => onFeatureNameChange(event.target.value)}
                    placeholder="例如：风控策略"
                    value={featureName}
                  />
                </label>
                <label className="field-label compact">
                  描述
                  <Textarea
                    onChange={(event) =>
                      onFeatureDescriptionChange(event.target.value)
                    }
                    placeholder="补充边界、负责人和常见问题"
                    value={featureDescription}
                  />
                </label>
                <Button
                  disabled={!featureName.trim() || createPending}
                  type="submit"
                  variant="primary"
                >
                  创建特性
                </Button>
              </form>
            ) : null}
            {isLoading ? <p className="empty-note">正在加载特性</p> : null}
            {!isLoading && visibleFeatures.length === 0 ? (
              <div className="empty-block">
                <p>暂无特性</p>
                <span>
                  点击右上角加号创建业务特性，再上传 Wiki、报告和仓库关联。
                </span>
              </div>
            ) : null}
            {visibleFeatures.map((feature) => (
              <FeatureListItem
                active={selectedFeatureId === feature.id}
                feature={feature}
                key={feature.id}
                onClick={() => onSelect(feature.id)}
                onDelete={() => onDelete(feature)}
                pendingDelete={pendingDelete}
              />
            ))}
          </div>
        </>
      )}
    </aside>
  );
}
