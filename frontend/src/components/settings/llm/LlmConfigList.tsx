import { Pencil, PlugZap, Trash2 } from "lucide-react";

import type { LLMConfigResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { SwitchControl } from "../SwitchControl";
import type { LlmUpdatePayload } from "../settings-types";
import { opencodeProviderLabel, protocolLabel } from "../settings-utils";
import { LlmConfigEditForm } from "./LlmConfigEditForm";

export function LlmConfigList({
  configs,
  deleting,
  editingId,
  onDelete,
  onEditCancel,
  onEditStart,
  onTest,
  onUpdate,
  onToggleEnabled,
  testingId,
  updating,
}: {
  configs: LLMConfigResponse[];
  deleting: boolean;
  editingId: string | null;
  onDelete: (id: string) => void;
  onEditCancel: () => void;
  onEditStart: (id: string) => void;
  onTest: (id: string) => void;
  onUpdate: (id: string, payload: LlmUpdatePayload) => void;
  onToggleEnabled: (config: LLMConfigResponse) => void;
  testingId: string | null;
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
                  OpenCode Provider:{" "}
                  {opencodeProviderLabel(config.opencode_provider_profile)} ·{" "}
                  {providerStatusLabel(config)}
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
                onSubmit={(payload) => onUpdate(config.id, payload)}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function providerStatusLabel(config: LLMConfigResponse) {
  if (config.opencode_provider_status === "ok") {
    return "连接正常";
  }
  if (config.opencode_provider_status === "failed") {
    return `连接失败${config.opencode_provider_error ? `：${config.opencode_provider_error}` : ""}`;
  }
  return "未测试";
}
