import { Pencil, PlugZap, Trash2 } from "lucide-react";

import type { LLMConfigResponse, LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { SwitchControl } from "../SwitchControl";
import type { LlmRuntimeProfileOption, LlmUpdatePayload } from "../settings-types";
import { agentRuntimeProfileLabel, protocolLabel } from "../settings-utils";
import { LlmConfigEditForm } from "./LlmConfigEditForm";

export function LlmConfigList({
  configs,
  deleting,
  editingId,
  onDelete,
  onEditCancel,
  onEditStart,
  onTest,
  onTestUpdateDraft,
  onUpdate,
  onToggleEnabled,
  runtimeProfileOptions,
  testingId,
  testingUpdateDraftId,
  updating,
}: {
  configs: LLMConfigResponse[];
  deleting: boolean;
  editingId: string | null;
  onDelete: (id: string) => void;
  onEditCancel: () => void;
  onEditStart: (id: string) => void;
  onTest: (id: string) => void;
  onTestUpdateDraft: (
    id: string,
    payload: LlmUpdatePayload,
  ) => Promise<LLMConfigTestResponse>;
  onUpdate: (id: string, payload: LlmUpdatePayload) => void;
  onToggleEnabled: (config: LLMConfigResponse) => void;
  runtimeProfileOptions: LlmRuntimeProfileOption[];
  testingId: string | null;
  testingUpdateDraftId: string | null;
  updating: boolean;
}) {
  if (configs.length === 0) {
    return (
      <div className="empty-block wide">
        <p>暂无 LLM 配置</p>
      </div>
    );
  }
  return (
    <ul className="data-list settings-config-list">
      {configs.map((config) => {
        const isEditing = editingId === config.id;
        return (
          <li data-editing={isEditing} key={config.id}>
            <div className="config-row-main">
              <div className="config-summary">
                <span>{config.name}</span>
                <small>
                  {protocolLabel(config.protocol)} · {config.model_name} ·{" "}
                  {config.api_key_masked}
                </small>
                <small>
                  Agent 适配方式:{" "}
                  {agentRuntimeProfileLabel(
                    config.agent_runtime_profile ?? config.opencode_provider_profile,
                    runtimeProfileOptions,
                  )}{" "}
                  ·{" "}
                  <span
                    className="provider-status-text"
                    title={providerStatusFullText(config)}
                  >
                    {providerStatusLabel(config)}
                  </span>
                </small>
              </div>
              <div className="row-actions">
                <SwitchControl
                  checked={config.enabled}
                  disabled={updating}
                  label={`${config.name} 启用状态`}
                  onChange={() => onToggleEnabled(config)}
                  text={config.enabled ? "启用" : "停用"}
                />
                <Button
                  aria-label={`编辑 ${config.name}`}
                  disabled={updating}
                  icon={<Pencil size={15} />}
                  onClick={() => onEditStart(config.id)}
                  type="button"
                  variant="quiet"
                >
                  编辑
                </Button>
                <Button
                  disabled={testingId === config.id}
                  icon={<PlugZap size={15} />}
                  onClick={() => onTest(config.id)}
                  type="button"
                  variant="quiet"
                >
                  {testingId === config.id ? "测试中" : "测试连接"}
                </Button>
                <Button
                  disabled={deleting}
                  icon={<Trash2 size={15} />}
                  onClick={() => onDelete(config.id)}
                  type="button"
                  variant="quiet"
                >
                  删除
                </Button>
              </div>
            </div>
            {isEditing ? (
              <LlmConfigEditForm
                config={config}
                disabled={updating}
                onCancel={onEditCancel}
                onTest={(payload) => onTestUpdateDraft(config.id, payload)}
                onSubmit={(payload) => onUpdate(config.id, payload)}
                runtimeProfileOptions={runtimeProfileOptions}
                testing={testingUpdateDraftId === config.id}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function providerStatusLabel(config: LLMConfigResponse) {
  const status = config.agent_runtime_status || config.opencode_provider_status;
  const error = config.agent_runtime_error ?? config.opencode_provider_error;
  if (status === "ok") {
    return "连接正常";
  }
  if (status === "failed") {
    return `连接失败${error ? `：${previewText(error)}` : ""}`;
  }
  return "未测试";
}

function providerStatusFullText(config: LLMConfigResponse) {
  const status = config.agent_runtime_status || config.opencode_provider_status;
  const error = config.agent_runtime_error ?? config.opencode_provider_error;
  if (status === "ok") {
    return "连接正常";
  }
  if (status === "failed") {
    return `连接失败${error ? `：${error}` : ""}`;
  }
  return "未测试";
}

function previewText(value: string, limit = 150) {
  const cleaned = value.replace(/\s+/g, " ").trim();
  if (cleaned.length <= limit) {
    return cleaned;
  }
  return `${cleaned.slice(0, limit - 3)}...`;
}
