import { Pencil, Trash2 } from "lucide-react";

import type { SkillResponse } from "../../types/api";
import { Button } from "../ui/button";
import { PolicyEditForm, type PolicyUpdatePayload } from "./PolicyForm";
import { stageLabel } from "./policy-options";

const PROMPT_PREVIEW_LIMIT = 180;

export function PolicyRow({
  editing,
  onCancel,
  onDelete,
  onEdit,
  onSubmit,
  onToggle,
  pending,
  policy,
  readOnly,
}: {
  editing: boolean;
  onCancel: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onSubmit: (payload: PolicyUpdatePayload) => void;
  onToggle: () => void;
  pending: boolean;
  policy: SkillResponse;
  readOnly?: boolean;
}) {
  if (editing && !readOnly) {
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

  const promptText = policy.prompt_template.trim();
  const promptPreview = formatPromptPreview(promptText);
  const hasFullPrompt =
    promptText.length > PROMPT_PREVIEW_LIMIT || promptText.includes("\n");

  return (
    <li className="policy-row" data-enabled={policy.enabled ? "true" : "false"}>
      <div className="policy-row-content">
        <div className="config-summary policy-summary">
          <span>{policy.name}</span>
          <div className="policy-meta-row">
            <span className="stage-chip">{stageLabel(policy.stage)}</span>
            <span className="policy-priority">
              优先级 <span className="console-mono">{policy.priority}</span>
            </span>
          </div>
        </div>
        <p className="policy-prompt-preview">{promptPreview}</p>
        {hasFullPrompt ? (
          <details className="policy-full-details">
            <summary role="button">查看完整策略</summary>
            <div className="policy-full-text">{promptText}</div>
          </details>
        ) : null}
      </div>
      <div className="row-actions">
        <PolicySwitch
          checked={policy.enabled}
          disabled={pending || Boolean(readOnly)}
          label={`${policy.name} 启用状态`}
          onChange={onToggle}
        />
        {!readOnly ? (
          <>
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
          </>
        ) : null}
      </div>
    </li>
  );
}

function formatPromptPreview(promptText: string) {
  const compactText = promptText.replace(/\s+/g, " ").trim();
  if (compactText.length <= PROMPT_PREVIEW_LIMIT) {
    return compactText;
  }
  return `${compactText.slice(0, PROMPT_PREVIEW_LIMIT)}...`;
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
