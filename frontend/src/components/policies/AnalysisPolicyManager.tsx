import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, SlidersHorizontal } from "lucide-react";

import {
  createSkill,
  deleteSkill,
  listSkills,
  updateSkill,
} from "../../lib/api";
import type { SkillResponse } from "../../types/api";
import { Button } from "../ui/button";
import { PolicyForm, type PolicyUpdatePayload } from "./PolicyForm";
import { PolicyRow } from "./PolicyRow";
import { mergeById } from "./policy-utils";

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
      payload: Partial<PolicyUpdatePayload & { enabled: boolean }>;
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
