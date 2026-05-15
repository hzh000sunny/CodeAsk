import { useState } from "react";
import type { FormEvent } from "react";
import { PlugZap } from "lucide-react";

import type { LLMConfigTestResponse } from "../../../types/api";
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
  opencode_provider_status?: "unknown" | "ok" | "failed";
  opencode_provider_tested_at?: string | null;
  opencode_provider_error?: string | null;
  opencode_provider_test_result_json?: unknown | null;
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
  onTest: (payload: LlmCreatePayload) => Promise<LLMConfigTestResponse>;
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
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  function clearTestResult() {
    setTestResult(null);
  }

  function resetCreateForm() {
    setConfigName("");
    setProtocol("openai");
    setBaseUrl("");
    setApiKey("");
    setModelName("");
    setEnabled(true);
    setOpencodeProviderProfile("default");
    setTestResult(null);
  }

  const payload: LlmCreatePayload = {
      name: configName.trim(),
      protocol,
      base_url: baseUrl.trim() || null,
      api_key: apiKey,
      model_name: modelName.trim(),
      enabled,
      reasoning_profile: "none",
      reasoning_profile_json: null,
      opencode_provider_profile: opencodeProviderProfile,
    };
  if (testResult) {
    payload.opencode_provider_status = testResult.status;
    payload.opencode_provider_tested_at = testResult.tested_at;
    payload.opencode_provider_error = testResult.error;
    payload.opencode_provider_test_result_json = testResult.result;
  }
  const canSubmit = Boolean(configName.trim() && apiKey && modelName.trim());

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(payload);
  }

  async function testCurrentForm() {
    const result = await onTest(payload);
    setTestResult(result);
  }

  return (
    <form className="inline-form llm-form llm-create-form" onSubmit={submit}>
      <label className="field-label compact">
        配置名称
        <Input
          onChange={(event) => {
            setConfigName(event.target.value);
            clearTestResult();
          }}
          value={configName}
        />
      </label>
      <label className="field-label compact">
        消息接口协议
        <select
          className="input"
          onChange={(event) => {
            setProtocol(event.target.value as LlmProtocol);
            clearTestResult();
          }}
          value={protocol}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </label>
      <label className="field-label compact">
        Base URL
        <Input
          onChange={(event) => {
            setBaseUrl(event.target.value);
            clearTestResult();
          }}
          value={baseUrl}
        />
      </label>
      <label className="field-label compact">
        API Key
        <Input
          onChange={(event) => {
            setApiKey(event.target.value);
            clearTestResult();
          }}
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        模型名称
        <Input
          onChange={(event) => {
            setModelName(event.target.value);
            clearTestResult();
          }}
          value={modelName}
        />
      </label>
      <label className="field-label compact">
        OpenCode Provider
        <select
          className="input"
          onChange={(event) => {
            setOpencodeProviderProfile(
              event.target.value as LlmOpenCodeProviderProfile,
            );
            clearTestResult();
          }}
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
          onClick={() => void testCurrentForm()}
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
