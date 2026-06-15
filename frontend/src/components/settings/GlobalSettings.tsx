import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Check, Paperclip } from "lucide-react";

import { getSystemSettings, updateSystemSettings } from "../../lib/api";
import { useAppFeedback } from "../feedback/AppFeedback";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { LlmConfigManager } from "./llm/LlmConfigManager";
import { OpencodeStatusPanel } from "./OpencodeStatusPanel";
import { OpencodeToolPermissionsPanel } from "./OpencodeToolPermissionsPanel";
import { RepoManager } from "./repos/RepoManager";
import { messageFromApiError } from "./settings-utils";
import { UserManager } from "./users/UserManager";

export function GlobalSettings() {
  return <SessionAttachmentSettings />;
}

export function SessionAttachmentSettings() {
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
    <div className="console-stack">
      <section className="surface">
        <div className="section-title">
          <Paperclip aria-hidden="true" size={18} />
          <h2>会话附件</h2>
        </div>

        <div className="console-toggle-row">
          <div className="console-toggle-text">
            <strong>附件上传入口</strong>
            <small>对所有会话的附件上传按钮生效</small>
          </div>
          <label
            className="switch-control"
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
              {attachmentsEnabled ? "开启" : "关闭"}
            </span>
          </label>
        </div>

        <div
          className="console-status-line"
          data-tone={attachmentsEnabled ? "ok" : "muted"}
        >
          {attachmentsEnabled ? (
            <Check aria-hidden="true" size={15} />
          ) : (
            <Ban aria-hidden="true" size={15} />
          )}
          <span>
            {attachmentsEnabled
              ? "附件上传已开启，所有会话均可上传附件。"
              : "附件上传已关闭，上传按钮仍保留，用户点击时会看到明确提示。"}
          </span>
        </div>
      </section>
    </div>
  );
}

export function AdminUsersSettings() {
  return <UserManager />;
}

export function AdminLlmSettings() {
  return <LlmConfigManager scope="global" />;
}

export function AdminRepoSettings() {
  return <RepoManager />;
}

export function AdminPolicySettings() {
  // 仅给设置页的策略管理套 console-stack 入场动效；特性页的同款组件不受影响。
  return (
    <div className="console-stack">
      <AnalysisPolicyManager
        description="全局策略会注入 Agent 上下文，约束问题定位、代码调查和最终回答。"
        scope="global"
        title="全局分析策略"
      />
    </div>
  );
}

export function AdminRuntimeSettings() {
  return (
    <div className="opencode-console">
      <OpencodeStatusPanel />
      <OpencodeToolPermissionsPanel />
    </div>
  );
}
