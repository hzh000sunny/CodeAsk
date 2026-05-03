import { useState } from "react";

import type { SkillResponse } from "../../types/api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { STAGE_OPTIONS } from "./policy-options";

export interface PolicyUpdatePayload {
  name: string;
  stage: string;
  priority: number;
  prompt_template: string;
}

export function PolicyForm({
  actionLabel,
  className,
  disabled,
  name,
  onCancel,
  onNameChange,
  onPriorityChange,
  onPromptChange,
  onStageChange,
  onSubmit,
  priority,
  promptTemplate,
  stage,
}: {
  actionLabel: string;
  className?: string;
  disabled: boolean;
  name: string;
  onCancel: () => void;
  onNameChange: (value: string) => void;
  onPriorityChange: (value: string) => void;
  onPromptChange: (value: string) => void;
  onStageChange: (value: string) => void;
  onSubmit: () => void;
  priority: string;
  promptTemplate: string;
  stage: string;
}) {
  return (
    <form
      className={`inline-form policy-form${className ? ` ${className}` : ""}`}
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="field-label compact">
        策略名称
        <Input
          onChange={(event) => onNameChange(event.target.value)}
          value={name}
        />
      </label>
      <label className="field-label compact">
        适用阶段
        <select
          className="input"
          onChange={(event) => onStageChange(event.target.value)}
          value={stage}
        >
          {STAGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="field-label compact">
        优先级
        <Input
          min="0"
          onChange={(event) => onPriorityChange(event.target.value)}
          type="number"
          value={priority}
        />
      </label>
      <label className="field-label compact policy-prompt-field">
        Prompt 内容
        <Textarea
          onChange={(event) => onPromptChange(event.target.value)}
          value={promptTemplate}
        />
      </label>
      <div className="form-actions">
        <Button disabled={disabled} type="submit" variant="primary">
          {actionLabel}
        </Button>
        <Button onClick={onCancel} type="button" variant="quiet">
          取消
        </Button>
      </div>
    </form>
  );
}

export function PolicyEditForm({
  disabled,
  onCancel,
  onSubmit,
  policy,
}: {
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (payload: PolicyUpdatePayload) => void;
  policy: SkillResponse;
}) {
  const [name, setName] = useState(policy.name);
  const [stage, setStage] = useState(policy.stage);
  const [priority, setPriority] = useState(String(policy.priority));
  const [promptTemplate, setPromptTemplate] = useState(policy.prompt_template);

  return (
    <PolicyForm
      actionLabel="保存分析策略"
      disabled={!name.trim() || !promptTemplate.trim() || disabled}
      name={name}
      onCancel={onCancel}
      onNameChange={setName}
      onPriorityChange={setPriority}
      onPromptChange={setPromptTemplate}
      onStageChange={setStage}
      onSubmit={() =>
        onSubmit({
          name: name.trim(),
          stage,
          priority: Number(priority) || 100,
          prompt_template: promptTemplate.trim(),
        })
      }
      priority={priority}
      promptTemplate={promptTemplate}
      stage={stage}
    />
  );
}
