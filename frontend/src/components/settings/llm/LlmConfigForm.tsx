import { useId, useState } from "react";
import type { FormEvent } from "react";
import { PlugZap, Plus, X } from "lucide-react";

import type { LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import { SwitchControl } from "../SwitchControl";
import type {
  LlmConfigMode,
  LlmHeaders,
  LlmProviderOption,
  LlmReasoningProfile,
} from "../settings-types";

export interface LlmCreatePayload {
  name: string;
  mode: LlmConfigMode;
  provider_id: string;
  base_url: string | null;
  api_key: string;
  headers: LlmHeaders | null;
  model_name: string;
  enabled: boolean;
  reasoning_profile: LlmReasoningProfile;
  reasoning_profile_json: string | null;
  opencode_provider_status?: "unknown" | "ok" | "failed";
  opencode_provider_tested_at?: string | null;
  opencode_provider_error?: string | null;
  opencode_provider_test_result_json?: unknown | null;
}

interface HeaderRow {
  key: string;
  value: string;
}

function rowsToHeaders(rows: HeaderRow[]): LlmHeaders | null {
  const entries = rows
    .map((row) => [row.key.trim(), row.value] as const)
    .filter(([key]) => key);
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

export function LlmConfigForm({
  disabled,
  onCancel,
  onTest,
  onSubmit,
  providerOptions = [],
  testing,
}: {
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmCreatePayload) => Promise<LLMConfigTestResponse>;
  onSubmit: (payload: LlmCreatePayload) => void;
  providerOptions?: LlmProviderOption[];
  testing: boolean;
}) {
  const datalistId = useId();
  const [configName, setConfigName] = useState("");
  const [providerId, setProviderId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [showHeaders, setShowHeaders] = useState(false);
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  function clearTestResult() {
    setTestResult(null);
  }

  function resetCreateForm() {
    setConfigName("");
    setProviderId("");
    setBaseUrl("");
    setApiKey("");
    setModelName("");
    setShowHeaders(false);
    setHeaderRows([]);
    setEnabled(true);
    setTestResult(null);
  }

  const payload: LlmCreatePayload = {
    name: configName.trim(),
    mode: "catalog",
    provider_id: providerId.trim(),
    base_url: baseUrl.trim() || null,
    api_key: apiKey,
    headers: rowsToHeaders(headerRows),
    model_name: modelName.trim(),
    enabled,
    reasoning_profile: "none",
    reasoning_profile_json: null,
  };
  if (testResult) {
    payload.opencode_provider_status = testResult.status;
    payload.opencode_provider_tested_at = testResult.tested_at;
    payload.opencode_provider_error = testResult.error;
    payload.opencode_provider_test_result_json = testResult.result;
  }
  const canSubmit = Boolean(
    configName.trim() && providerId.trim() && apiKey && modelName.trim(),
  );

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
      <datalist id={datalistId}>
        {providerOptions.map((option) => (
          <option key={option.id} value={option.id} />
        ))}
      </datalist>
      <div className="form-row">
        <label className="field-label compact">
          provider
          <Input
            className="console-mono"
            list={datalistId}
            onChange={(event) => {
              setProviderId(event.target.value);
              clearTestResult();
            }}
            placeholder="deepseek / openai / anthropic …"
            value={providerId}
          />
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
        <span className="field-hint">可选 · 留空走目录默认端点；填入即作为网关地址</span>
        <Input
          aria-label="Base URL"
          className="console-mono"
          onChange={(event) => {
            setBaseUrl(event.target.value);
            clearTestResult();
          }}
          placeholder="https://..."
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
      {showHeaders ? (
        <div className="field-label compact">
          自定义请求头
          <span className="field-hint">网关需要非 Bearer 鉴权头时填写</span>
          <div className="kv-editor">
            {headerRows.map((row, index) => (
              <div className="kv-row" key={index}>
                <Input
                  aria-label={`请求头 ${index + 1} 名称`}
                  className="console-mono"
                  onChange={(event) => {
                    const next = [...headerRows];
                    next[index] = { ...row, key: event.target.value };
                    setHeaderRows(next);
                    clearTestResult();
                  }}
                  placeholder="Header"
                  value={row.key}
                />
                <Input
                  aria-label={`请求头 ${index + 1} 值`}
                  className="console-mono"
                  onChange={(event) => {
                    const next = [...headerRows];
                    next[index] = { ...row, value: event.target.value };
                    setHeaderRows(next);
                    clearTestResult();
                  }}
                  placeholder="value"
                  value={row.value}
                />
                <button
                  aria-label={`删除请求头 ${index + 1}`}
                  className="kv-remove"
                  onClick={() => {
                    setHeaderRows(headerRows.filter((_, i) => i !== index));
                    clearTestResult();
                  }}
                  type="button"
                >
                  <X aria-hidden="true" size={15} />
                </button>
              </div>
            ))}
            <button
              className="kv-add"
              onClick={() => setHeaderRows([...headerRows, { key: "", value: "" }])}
              type="button"
            >
              <Plus aria-hidden="true" size={14} />
              添加请求头
            </button>
          </div>
        </div>
      ) : (
        <button
          className="kv-add llm-advanced-toggle"
          onClick={() => {
            setShowHeaders(true);
            if (headerRows.length === 0) {
              setHeaderRows([{ key: "", value: "" }]);
            }
          }}
          type="button"
        >
          <Plus aria-hidden="true" size={14} />
          高级：自定义请求头
        </button>
      )}
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
