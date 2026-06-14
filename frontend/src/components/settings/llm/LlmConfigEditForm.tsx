import { useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, Check, PlugZap } from "lucide-react";

import type { LLMConfigResponse, LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type {
  LlmOpenCodeProviderProfile,
  LlmProtocol,
  LlmRuntimeProfileOption,
  LlmUpdatePayload,
} from "../settings-types";
import {
  FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS,
  safeAgentRuntimeProfile,
  safeEditableProtocol,
} from "../settings-utils";

export function LlmConfigEditForm({
  config,
  disabled,
  onCancel,
  onTest,
  onSubmit,
  runtimeProfileOptions = FALLBACK_AGENT_RUNTIME_PROFILE_OPTIONS,
  testing,
}: {
  config: LLMConfigResponse;
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmUpdatePayload) => Promise<LLMConfigTestResponse>;
  onSubmit: (payload: LlmUpdatePayload) => void;
  runtimeProfileOptions?: LlmRuntimeProfileOption[];
  testing: boolean;
}) {
  const [name, setName] = useState(config.name);
  const [protocol, setProtocol] = useState<LlmProtocol>(
    safeEditableProtocol(config.protocol),
  );
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState(config.model_name);
  const initialRuntimeProfile =
    config.agent_runtime_profile ?? config.opencode_provider_profile;
  const [agentRuntimeProfile, setAgentRuntimeProfile] =
    useState<LlmOpenCodeProviderProfile>(
      safeAgentRuntimeProfile(
        initialRuntimeProfile,
        runtimeProfileOptions,
      ),
    );
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  function clearTestResult() {
    setTestResult(null);
  }

  const normalizedBaseUrl = baseUrl.trim() || null;
  const payload: LlmUpdatePayload = {};
  if (name.trim() !== config.name) {
    payload.name = name.trim();
  }
  if (protocol !== config.protocol) {
    payload.protocol = protocol;
  }
  if (normalizedBaseUrl !== config.base_url) {
    payload.base_url = normalizedBaseUrl;
  }
  if (modelName.trim() !== config.model_name) {
    payload.model_name = modelName.trim();
  }
  if (agentRuntimeProfile !== (initialRuntimeProfile || "default")) {
    payload.agent_runtime_profile = agentRuntimeProfile;
  }
  if (apiKey) {
    payload.api_key = apiKey;
  }
  if (testResult) {
    payload.opencode_provider_status = testResult.status;
    payload.opencode_provider_tested_at = testResult.tested_at;
    payload.opencode_provider_error = testResult.error;
    payload.opencode_provider_test_result_json = testResult.result;
  }
  const canSubmit = Boolean(name.trim() && modelName.trim());

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit(payload);
  }

  async function testCurrentForm() {
    const result = await onTest(payload);
    setTestResult(result);
  }

  return (
    <form className="inline-form llm-form llm-edit-form" onSubmit={submit}>
      <label className="field-label compact">
        编辑配置名称
        <Input
          onChange={(event) => {
            setName(event.target.value);
            clearTestResult();
          }}
          value={name}
        />
      </label>
      <div className="form-row">
        <label className="field-label compact">
          编辑消息接口协议
          <select
            className="input"
            onChange={(event) => {
              setProtocol(event.target.value as LlmProtocol);
              clearTestResult();
            }}
            value={protocol}
          >
            <option value="openai">OpenAI</option>
            {protocol === "openai_compatible" ? (
              <option value="openai_compatible">OpenAI Compatible (历史)</option>
            ) : null}
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
        <label className="field-label compact">
          编辑模型名称
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
        编辑 Base URL
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
        编辑 API Key
        <Input
          className="console-mono"
          onChange={(event) => {
            setApiKey(event.target.value);
            clearTestResult();
          }}
          placeholder="留空则不修改"
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        编辑 Agent 适配方式
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
      <div className="form-actions llm-edit-actions">
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
          保存修改
        </Button>
        <Button disabled={disabled} onClick={onCancel} type="button" variant="quiet">
          取消
        </Button>
      </div>
    </form>
  );
}
