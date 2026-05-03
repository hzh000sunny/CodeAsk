import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";

import {
  createAdminLlmConfig,
  createUserLlmConfig,
  deleteAdminLlmConfig,
  deleteUserLlmConfig,
  listAdminLlmConfigs,
  listUserLlmConfigs,
  updateAdminLlmConfig,
  updateUserLlmConfig,
} from "../../../lib/api";
import type { LLMConfigResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import type { LlmScope, LlmUpdatePayload } from "../settings-types";
import { messageFromApiError } from "../settings-utils";
import { LlmConfigForm, type LlmCreatePayload } from "./LlmConfigForm";
import { LlmConfigList } from "./LlmConfigList";

export function LlmConfigManager({ scope }: { scope: LlmScope }) {
  const queryClient = useQueryClient();
  const noticeTimeoutRef = useRef<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "success" | "danger";
    message: string;
  } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const queryKey =
    scope === "global" ? ["admin-llm-configs"] : ["user-llm-configs"];
  const { data: configs = [] } = useQuery({
    queryKey,
    queryFn: scope === "global" ? listAdminLlmConfigs : listUserLlmConfigs,
  });

  useEffect(() => {
    return () => {
      if (noticeTimeoutRef.current) {
        window.clearTimeout(noticeTimeoutRef.current);
      }
    };
  }, []);

  const createMutation = useMutation({
    mutationFn: (payload: LlmCreatePayload) =>
      scope === "global"
        ? createAdminLlmConfig(payload)
        : createUserLlmConfig(payload),
    onSuccess: () => {
      showNotice("success", "LLM 配置已保存");
      setShowForm(false);
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `保存 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: LlmUpdatePayload }) =>
      scope === "global"
        ? updateAdminLlmConfig(id, payload)
        : updateUserLlmConfig(id, payload),
    onSuccess: () => {
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `更新 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      scope === "global" ? deleteAdminLlmConfig(id) : deleteUserLlmConfig(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `删除 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });

  function showNotice(tone: "success" | "danger", message: string) {
    if (noticeTimeoutRef.current) {
      window.clearTimeout(noticeTimeoutRef.current);
    }
    setNotice({ tone, message });
    noticeTimeoutRef.current = window.setTimeout(() => {
      setNotice(null);
      noticeTimeoutRef.current = null;
    }, 3200);
  }

  return (
    <section className="surface">
      <div className="section-title">
        <KeyRound aria-hidden="true" size={18} />
        <h2>{scope === "global" ? "全局 LLM 配置" : "个人 LLM 配置"}</h2>
      </div>
      <div className="content-toolbar slim">
        <p>
          {scope === "global"
            ? "管理员可维护多个全局账号，启用状态决定是否参与运行时选择。"
            : "个人配置优先于全局配置，用于覆盖自己的模型账号。"}
        </p>
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowForm((value) => !value)}
          type="button"
          variant="primary"
        >
          添加 LLM 配置
        </Button>
      </div>
      {notice ? (
        <div
          className="settings-toast"
          data-tone={notice.tone}
          role={notice.tone === "danger" ? "alert" : "status"}
        >
          {notice.message}
        </div>
      ) : null}
      {showForm ? (
        <LlmConfigForm
          disabled={createMutation.isPending}
          onCancel={() => setShowForm(false)}
          onSubmit={(payload) => createMutation.mutate(payload)}
        />
      ) : null}
      <LlmConfigList
        configs={configs as LLMConfigResponse[]}
        deleting={deleteMutation.isPending}
        editingId={editingId}
        onDelete={(id) => deleteMutation.mutate(id)}
        onEditCancel={() => setEditingId(null)}
        onEditStart={(id) => setEditingId(id)}
        onUpdate={(id, payload) => updateMutation.mutate({ id, payload })}
        onToggleEnabled={(config) =>
          updateMutation.mutate({
            id: config.id,
            payload: { enabled: !config.enabled },
          })
        }
        updating={updateMutation.isPending}
      />
    </section>
  );
}
