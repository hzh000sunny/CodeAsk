import { useState } from "react";
import type { FormEvent } from "react";
import { PlugZap } from "lucide-react";

import type { LLMConfigResponse, LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type {
  LlmOpenCodeProviderProfile,
  LlmProtocol,
  LlmUpdatePayload,
} from "../settings-types";
import {
  OPENCODE_PROVIDER_PROFILE_OPTIONS,
  safeEditableProtocol,
  safeOpenCodeProviderProfile,
} from "../settings-utils";

export function LlmConfigEditForm({
  config,
  disabled,
  onCancel,
  onTest,
  onSubmit,
  testing,
}: {
  config: LLMConfigResponse;
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmUpdatePayload) => Promise<LLMConfigTestResponse>;
  onSubmit: (payload: LlmUpdatePayload) => void;
  testing: boolean;
}) {
  const [name, setName] = useState(config.name);
  const [protocol, setProtocol] = useState<LlmProtocol>(
    safeEditableProtocol(config.protocol),
  );
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState(config.model_name);
  const [opencodeProviderProfile, setOpencodeProviderProfile] =
    useState<LlmOpenCodeProviderProfile>(
      safeOpenCodeProviderProfile(config.opencode_provider_profile),
    );
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  function clearTestResult() {
    setTestResult(null);
  }

  const payload: LlmUpdatePayload = {
      name: name.trim(),
      protocol,
      base_url: baseUrl.trim() || null,
      model_name: modelName.trim(),
      opencode_provider_profile: opencodeProviderProfile,
    };
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
          <option value="anthropic">Anthropic</option>
        </select>
      </label>
      <label className="field-label compact">
        编辑 Base URL
        <Input
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
        编辑模型名称
        <Input
          onChange={(event) => {
            setModelName(event.target.value);
            clearTestResult();
          }}
          value={modelName}
        />
      </label>
      <label className="field-label compact">
        编辑 OpenCode Provider
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
