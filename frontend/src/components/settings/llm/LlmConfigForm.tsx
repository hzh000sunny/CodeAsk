import { useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, Check, PlugZap } from "lucide-react";

import type { LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { SwitchControl } from "../SwitchControl";
import type {
  LlmOpenCodeProviderProfile,
  LlmProtocol,
  LlmReasoningProfile,
  LlmRuntimeProfileOption,
} from "../settings-types";
import { FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS } from "../settings-utils";

export interface LlmCreatePayload {
  name: string;
  protocol: LlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  enabled: boolean;
  reasoning_profile: LlmReasoningProfile;
  reasoning_profile_json: string | null;
  agent_runtime_profile: LlmOpenCodeProviderProfile;
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
  runtimeProfileOptions = FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS,
  testing,
}: {
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmCreatePayload) => Promise<LLMConfigTestResponse>;
  onSubmit: (payload: LlmCreatePayload) => void;
  runtimeProfileOptions?: LlmRuntimeProfileOption[];
  testing: boolean;
}) {
  const [configName, setConfigName] = useState("");
  const [protocol, setProtocol] = useState<LlmProtocol>("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [agentRuntimeProfile, setAgentRuntimeProfile] =
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
    setAgentRuntimeProfile("default");
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
    agent_runtime_profile: agentRuntimeProfile,
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
      <div className="form-row">
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
          模型名称
          <Input
            className="console-mono"
            onChange={(event) => {
              setModelName(event.target.value);
              clearTestResult();
            }}
            value={modelName}
          />
        </label>
      </div>
      <label className="field-label compact">
        Base URL
        <Input
          className="console-mono"
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
          className="console-mono"
          onChange={(event) => {
            setApiKey(event.target.value);
            clearTestResult();
          }}
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        Agent 适配方式
        <select
          className="input"
          onChange={(event) => {
            setAgentRuntimeProfile(
              event.target.value as LlmOpenCodeProviderProfile,
            );
            clearTestResult();
          }}
          value={agentRuntimeProfile}
        >
          {runtimeProfileOptions.map((option) => (
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
      {testResult ? (
        <div
          className="console-status-line"
          data-tone={testResult.status === "ok" ? "ok" : "error"}
        >
          {testResult.status === "ok" ? (
            <Check aria-hidden="true" size={15} />
          ) : (
            <AlertTriangle aria-hidden="true" size={15} />
          )}
          <span>
            {testResult.status === "ok"
              ? `连接正常${testResult.profile_id ? ` · ${testResult.profile_id}` : ""}`
              : `连接失败：${testResult.error ?? "未知错误"}`}
          </span>
        </div>
      ) : null}
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
