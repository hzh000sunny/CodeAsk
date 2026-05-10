import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Paperclip } from "lucide-react";

import { getSystemSettings, updateSystemSettings } from "../../lib/api";
import { useAppFeedback } from "../feedback/AppFeedback";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { LlmConfigManager } from "./llm/LlmConfigManager";
import { RepoManager } from "./repos/RepoManager";
import { messageFromApiError } from "./settings-utils";
import { UserManager } from "./users/UserManager";

export function GlobalSettings() {
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAppFeedback();
  const settingsQuery = useQuery({
    queryKey: ["system-settings"],
    queryFn: getSystemSettings,
  });
  const updateMutation = useMutation({
    mutationFn: updateSystemSettings,
    onSuccess: (settings) => {
      queryClient.setQueryData(["system-settings"], settings);
      showSuccess("全局配置已保存");
    },
    onError: (error) => showError(`保存全局配置失败：${messageFromApiError(error)}`),
  });
  const attachmentsEnabled =
    settingsQuery.data?.session_attachments_enabled ?? true;

  return (
    <div className="settings-stack">
      <section className="surface">
        <div className="section-title">
          <Paperclip aria-hidden="true" size={18} />
          <h2>会话附件</h2>
        </div>
        <label
          className="switch-control settings-toggle-row"
          data-checked={attachmentsEnabled}
          data-disabled={updateMutation.isPending ? "true" : "false"}
        >
          <input
            aria-label="会话附件上传开关"
            checked={attachmentsEnabled}
            disabled={updateMutation.isPending}
            onChange={(event) =>
              updateMutation.mutate({
                session_attachments_enabled: event.target.checked,
              })
            }
            role="switch"
            type="checkbox"
          />
          <span aria-hidden="true" className="switch-track" />
          <span className="switch-text">
            {attachmentsEnabled ? "允许上传附件" : "已禁用附件上传"}
          </span>
        </label>
      </section>
      <UserManager />
      <LlmConfigManager scope="global" />
      <RepoManager />
      <AnalysisPolicyManager
        description="全局策略会注入 Agent 上下文，约束问题定位、代码调查和最终回答。"
        scope="global"
        title="全局分析策略"
      />
    </div>
  );
}
