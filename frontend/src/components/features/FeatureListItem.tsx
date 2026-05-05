import { Trash2 } from "lucide-react";

import type { FeatureRead } from "../../types/api";

export function FeatureListItem({
  active,
  feature,
  onClick,
  onDelete,
  pendingDelete,
}: {
  active: boolean;
  feature: FeatureRead;
  onClick: () => void;
  onDelete: () => void;
  pendingDelete: boolean;
}) {
  return (
    <div className="list-row" data-active={active}>
      <button
        className="list-item"
        data-active={active}
        onClick={onClick}
        type="button"
      >
        <span className="item-title">{feature.name}</span>
        {feature.description ? (
          <span className="item-meta feature-item-description">{feature.description}</span>
        ) : null}
      </button>
      <button
        aria-label={`删除特性 ${feature.name}`}
        className="list-delete-button"
        disabled={pendingDelete}
        onClick={onDelete}
        title="删除特性"
        type="button"
      >
        <Trash2 aria-hidden="true" size={15} />
      </button>
    </div>
  );
}
