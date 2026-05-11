import { Pencil, Trash2 } from "lucide-react";

import type { LLMConfigResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { SwitchControl } from "../SwitchControl";
import type { LlmUpdatePayload } from "../settings-types";
import { protocolLabel } from "../settings-utils";
import { LlmConfigEditForm } from "./LlmConfigEditForm";

export function LlmConfigList({
  configs,
  deleting,
  editingId,
  onDelete,
  onEditCancel,
  onEditStart,
  onUpdate,
  onToggleEnabled,
  updating,
}: {
  configs: LLMConfigResponse[];
  deleting: boolean;
  editingId: string | null;
  onDelete: (id: string) => void;
  onEditCancel: () => void;
  onEditStart: (id: string) => void;
  onUpdate: (id: string, payload: LlmUpdatePayload) => void;
  onToggleEnabled: (config: LLMConfigResponse) => void;
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
