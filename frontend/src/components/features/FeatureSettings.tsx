import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, SlidersHorizontal } from "lucide-react";

import { updateFeature } from "../../lib/api";
import type { FeatureRead } from "../../types/api";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Textarea } from "../ui/textarea";
import { mergeById, messageFromError } from "./feature-utils";

export function FeatureSettings({
  canManageFeature,
  feature,
}: {
  canManageFeature: boolean;
  feature: FeatureRead | null;
}) {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAppFeedback();
  const [name, setName] = useState(feature?.name ?? "");
  const [description, setDescription] = useState(feature?.description ?? "");

  // 切换特性（或保存后 refetch 带回新值）时把表单重置回服务端真值，
  // 避免上一条特性的编辑残留串台。以 feature.id + 服务端字段为 key。
  useEffect(() => {
    setName(feature?.name ?? "");
    setDescription(feature?.description ?? "");
  }, [feature?.id, feature?.name, feature?.description]);

  const savedName = feature?.name ?? "";
  const savedDescription = feature?.description ?? "";
  const trimmedName = name.trim();
  const dirty =
    name !== savedName || description !== savedDescription;

  const saveMutation = useMutation({
    mutationFn: () =>
      updateFeature(feature?.id as number, {
        name: trimmedName,
        description: description.trim(),
      }),
    onSuccess: (updated) => {
      // 本地立刻把列表缓存里的这条替换掉，标题/描述同步刷新，不等 refetch。
      queryClient.setQueryData<FeatureRead[]>(["features"], (current = []) =>
        mergeById(current, [updated]),
      );
      showSuccess("特性已保存");
      void queryClient.invalidateQueries({ queryKey: ["features"] });
    },
    onError: (error) => {
      showError(`保存特性失败：${messageFromError(error)}`);
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!feature || !trimmedName || !dirty) {
      return;
    }
    saveMutation.mutate();
  }

  const editable = Boolean(feature) && canManageFeature;

  return (
    <div className="tab-content two-column feature-settings-content">
      <section className="surface">
        <div className="section-title">
          <SlidersHorizontal aria-hidden="true" size={18} />
          <h2>特性设置</h2>
        </div>
        {!feature ? (
          <p className="empty-note">选择一个特性后查看与编辑其设置。</p>
        ) : editable ? (
          <form className="feature-settings-form" onSubmit={onSubmit}>
            <label className="field-label">
              名称
              <Input
                onChange={(event) => setName(event.target.value)}
                placeholder="特性名称"
                value={name}
              />
            </label>
            <label className="field-label">
              描述
              <Textarea
                onChange={(event) => setDescription(event.target.value)}
                placeholder="维护特性的业务边界和常见问题"
                value={description}
              />
            </label>
            <div className="feature-settings-actions">
              <Button
                disabled={!dirty || !trimmedName || saveMutation.isPending}
                type="submit"
                variant="primary"
              >
                {saveMutation.isPending ? "保存中" : "保存修改"}
              </Button>
            </div>
          </form>
        ) : (
          // 无管理权限：纯展示，不再用假装可编辑的只读输入框误导。
          <dl className="feature-readonly-fields">
            <dt>名称</dt>
            <dd>{savedName || "—"}</dd>
            <dt>描述</dt>
            <dd className={savedDescription ? undefined : "is-empty"}>
              {savedDescription || "暂无描述"}
            </dd>
          </dl>
        )}
      </section>
      <section className="surface">
        <div className="section-title">
          <ShieldCheck aria-hidden="true" size={18} />
          <h2>治理信息</h2>
        </div>
        <dl className="meta-grid">
          <dt>Owner</dt>
          <dd>{feature?.owner_subject_id ?? "未创建"}</dd>
          <dt>配置权限</dt>
          <dd>{canManageFeature ? "可管理" : "只读"}</dd>
          <dt>更新时间</dt>
          <dd>
            {feature ? new Date(feature.updated_at).toLocaleString() : "-"}
          </dd>
        </dl>
      </section>
    </div>
  );
}
