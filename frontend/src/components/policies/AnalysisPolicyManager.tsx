import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, SlidersHorizontal, Trash2 } from "lucide-react";

import {
  createSkill,
  deleteSkill,
  listSkills,
  updateSkill,
} from "../../lib/api";
import type { SkillResponse } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";

const STAGE_OPTIONS = [
  { value: "all", label: "全流程" },
  { value: "scope_detection", label: "范围判断" },
  { value: "knowledge_retrieval", label: "知识检索" },
  { value: "sufficiency_judgement", label: "充分性判断" },
  { value: "code_investigation", label: "代码调查" },
  { value: "answer_finalization", label: "最终回答" },
  { value: "report_drafting", label: "报告生成" },
];

interface AnalysisPolicyManagerProps {
  description?: string;
  featureId?: number;
  scope: "global" | "feature";
  title: string;
}

export function AnalysisPolicyManager({
  description,
  featureId,
  scope,
  title,
}: AnalysisPolicyManagerProps) {
  const queryClient = useQueryClient();
  const [createdPolicies, setCreatedPolicies] = useState<SkillResponse[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [stage, setStage] = useState("all");
  const [priority, setPriority] = useState("100");
  const [promptTemplate, setPromptTemplate] = useState("");
  const { data: fetchedPolicies = [] } = useQuery({
    queryKey: ["skills"],
    queryFn: listSkills,
  });
  const policies = mergeById(fetchedPolicies, createdPolicies).filter(
    (policy) =>
      policy.scope === scope &&
      (scope === "global"
        ? policy.feature_id === null
        : policy.feature_id === featureId),
  );
  const createMutation = useMutation({
    mutationFn: () =>
      createSkill({
        name: name.trim(),
        scope,
        feature_id: scope === "feature" ? featureId : null,
        stage,
        enabled: true,
        priority: Number(priority) || 100,
        prompt_template: promptTemplate.trim(),
      }),
    onSuccess: (policy) => {
      setCreatedPolicies((current) => mergeById(current, [policy]));
      setShowForm(false);
      setName("");
      setStage("all");
      setPriority("100");
      setPromptTemplate("");
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({
      policyId,
      payload,
    }: {
      policyId: string;
      payload: Partial<{
        name: string;
        stage: string;
        enabled: boolean;
        priority: number;
        prompt_template: string;
      }>;
    }) => updateSkill(policyId, payload),
    onSuccess: (policy) => {
      setCreatedPolicies((current) => mergeById(current, [policy]));
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteSkill,
    onSuccess: (_unused, policyId) => {
      setCreatedPolicies((current) =>
        current.filter((policy) => policy.id !== policyId),
      );
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });

  return (
    <section className="surface">
      <div className="section-title">
        <SlidersHorizontal aria-hidden="true" size={18} />
        <h2>{title}</h2>
      </div>
      <div className="content-toolbar slim">
        {description ? (
          <p>{description}</p>
        ) : (
          <p>配置注入 Agent 上下文的分析策略。</p>
        )}
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowForm((value) => !value)}
          type="button"
          variant="primary"
        >
          添加分析策略
        </Button>
      </div>
      {showForm ? (
        <PolicyForm
          actionLabel="创建分析策略"
          className="policy-create-form"
          disabled={
            !name.trim() ||
            !promptTemplate.trim() ||
            (scope === "feature" && !featureId) ||
            createMutation.isPending
          }
          name={name}
          onCancel={() => setShowForm(false)}
          onNameChange={setName}
          onPriorityChange={setPriority}
          onPromptChange={setPromptTemplate}
          onStageChange={setStage}
          onSubmit={() => createMutation.mutate()}
          priority={priority}
          promptTemplate={promptTemplate}
          stage={stage}
        />
      ) : null}
      {policies.length === 0 ? (
        <div className="empty-block wide">
          <p>暂无分析策略</p>
        </div>
      ) : (
        <ul className="data-list settings-config-list">
          {policies.map((policy) => (
            <PolicyRow
              editing={editingId === policy.id}
              key={policy.id}
              onCancel={() => setEditingId(null)}
              onDelete={() => deleteMutation.mutate(policy.id)}
              onEdit={() => setEditingId(policy.id)}
              onSubmit={(payload) =>
                updateMutation.mutate({ policyId: policy.id, payload })
              }
              onToggle={() =>
                updateMutation.mutate({
                  policyId: policy.id,
                  payload: { enabled: !policy.enabled },
                })
              }
              pending={updateMutation.isPending || deleteMutation.isPending}
              policy={policy}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function PolicyRow({
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
  onSubmit: (payload: {
    name: string;
    stage: string;
    priority: number;
    prompt_template: string;
  }) => void;
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

function PolicyForm({
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

function PolicyEditForm({
  disabled,
  onCancel,
  onSubmit,
  policy,
}: {
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (payload: {
    name: string;
    stage: string;
    priority: number;
    prompt_template: string;
  }) => void;
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

function stageLabel(stage: string) {
  return STAGE_OPTIONS.find((option) => option.value === stage)?.label ?? stage;
}

function mergeById<T extends { id: string | number }>(left: T[], right: T[]) {
  const rows = new Map<string | number, T>();
  for (const item of left) {
    rows.set(item.id, item);
  }
  for (const item of right) {
    rows.set(item.id, item);
  }
  return [...rows.values()];
}
