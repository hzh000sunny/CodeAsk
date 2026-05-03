import { Pencil, Trash2 } from "lucide-react";

import type { SkillResponse } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { PolicyEditForm, type PolicyUpdatePayload } from "./PolicyForm";
import { stageLabel } from "./policy-options";

export function PolicyRow({
  editing,
  onCancel,
  onDelete,
  onEdit,
  onSubmit,
  onToggle,
  pending,
  policy,
}: {
  editing: boolean;
  onCancel: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onSubmit: (payload: PolicyUpdatePayload) => void;
  onToggle: () => void;
  pending: boolean;
  policy: SkillResponse;
}) {
  if (editing) {
    return (
      <li data-editing="true">
        <PolicyEditForm
          disabled={pending}
          onCancel={onCancel}
          onSubmit={onSubmit}
          policy={policy}
        />
      </li>
    );
  }

  return (
    <li>
      <div className="config-summary">
        <span>{policy.name}</span>
        <small>
          {stageLabel(policy.stage)} · 优先级 {policy.priority} ·{" "}
          {policy.prompt_template}
        </small>
      </div>
      <div className="row-actions">
        <PolicySwitch
          checked={policy.enabled}
          disabled={pending}
          label={`${policy.name} 启用状态`}
          onChange={onToggle}
        />
        <Badge>{policy.scope === "global" ? "全局" : "特性"}</Badge>
        <Button
          aria-label={`编辑分析策略 ${policy.name}`}
          disabled={pending}
          icon={<Pencil size={15} />}
          onClick={onEdit}
          type="button"
          variant="quiet"
        >
          编辑
        </Button>
        <Button
          aria-label={`删除分析策略 ${policy.name}`}
          disabled={pending}
          icon={<Trash2 size={15} />}
          onClick={onDelete}
          type="button"
          variant="quiet"
        >
          删除
        </Button>
      </div>
    </li>
  );
}

function PolicySwitch({
  checked,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  disabled: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label
      className="switch-control"
      data-checked={checked}
      data-disabled={disabled ? "true" : "false"}
    >
      <input
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        role="switch"
        type="checkbox"
      />
      <span aria-hidden="true" className="switch-track" />
      <span className="switch-text">{checked ? "启用" : "停用"}</span>
    </label>
  );
}
