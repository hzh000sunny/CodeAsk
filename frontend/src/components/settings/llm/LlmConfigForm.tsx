import { useState } from "react";
import type { FormEvent } from "react";
import { PlugZap } from "lucide-react";

import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { SwitchControl } from "../SwitchControl";
import type {
  LlmOpenCodeProviderProfile,
  LlmProtocol,
  LlmReasoningProfile,
} from "../settings-types";
import { OPENCODE_PROVIDER_PROFILE_OPTIONS } from "../settings-utils";

export interface LlmCreatePayload {
  name: string;
  protocol: LlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  enabled: boolean;
  reasoning_profile: LlmReasoningProfile;
  reasoning_profile_json: string | null;
  opencode_provider_profile: LlmOpenCodeProviderProfile;
}

export function LlmConfigForm({
  disabled,
  onCancel,
  onTest,
  onSubmit,
  testing,
}: {
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmCreatePayload) => void;
  onSubmit: (payload: LlmCreatePayload) => void;
  testing: boolean;
}) {
  const [configName, setConfigName] = useState("");
  const [protocol, setProtocol] = useState<LlmProtocol>("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [opencodeProviderProfile, setOpencodeProviderProfile] =
    useState<LlmOpenCodeProviderProfile>("default");

  function resetCreateForm() {
    setConfigName("");
    setProtocol("openai");
    setBaseUrl("");
    setApiKey("");
    setModelName("");
    setEnabled(true);
    setOpencodeProviderProfile("default");
  }

  const payload = {
      name: configName.trim(),
      protocol,
      base_url: baseUrl.trim() || null,
      api_key: apiKey,
      model_name: modelName.trim(),
      enabled,
      reasoning_profile: "none",
      reasoning_profile_json: null,
      opencode_provider_profile: opencodeProviderProfile,
    } satisfies LlmCreatePayload;
  const canSubmit = Boolean(configName.trim() && apiKey && modelName.trim());

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(payload);
  }

  return (
    <form className="inline-form llm-form llm-create-form" onSubmit={submit}>
      <label className="field-label compact">
        配置名称
        <Input
          onChange={(event) => setConfigName(event.target.value)}
          value={configName}
        />
      </label>
      <label className="field-label compact">
        消息接口协议
        <select
          className="input"
          onChange={(event) => setProtocol(event.target.value as LlmProtocol)}
          value={protocol}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </label>
      <label className="field-label compact">
        Base URL
        <Input onChange={(event) => setBaseUrl(event.target.value)} value={baseUrl} />
      </label>
      <label className="field-label compact">
        API Key
        <Input
          onChange={(event) => setApiKey(event.target.value)}
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        模型名称
        <Input
          onChange={(event) => setModelName(event.target.value)}
          value={modelName}
        />
      </label>
      <label className="field-label compact">
        OpenCode Provider
        <select
          className="input"
          onChange={(event) =>
            setOpencodeProviderProfile(
              event.target.value as LlmOpenCodeProviderProfile,
            )
          }
          value={opencodeProviderProfile}
        >
          {OPENCODE_PROVIDER_PROFILE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <div className="form-switches">
        <SwitchControl
          checked={enabled}
          label="新配置启用状态"
          onChange={setEnabled}
          text={enabled ? "启用" : "停用"}
        />
      </div>
      <div className="form-actions">
        <Button
          disabled={!canSubmit || disabled || testing}
          icon={<PlugZap size={15} />}
          onClick={() => onTest(payload)}
          type="button"
          variant="secondary"
        >
          {testing ? "测试中" : "测试连接"}
        </Button>
        <Button
          disabled={!canSubmit || disabled}
          type="submit"
          variant="primary"
        >
          保存 LLM 配置
        </Button>
        <Button
          disabled={disabled}
          onClick={() => {
            resetCreateForm();
            onCancel();
          }}
          type="button"
          variant="quiet"
        >
          取消
        </Button>
      </div>
    </form>
  );
}
