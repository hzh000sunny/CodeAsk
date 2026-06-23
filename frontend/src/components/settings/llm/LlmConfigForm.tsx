import { useId, useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, Check, PlugZap, Plus, X } from "lucide-react";

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
import { sanitizeProviderSlug } from "../settings-utils";

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
  const [mode, setMode] = useState<LlmConfigMode>("catalog");
  const [providerId, setProviderId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>([]);
  const [enabled, setEnabled] = useState(true);
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  function clearTestResult() {
    setTestResult(null);
  }

  function resetCreateForm() {
    setConfigName("");
    setMode("catalog");
    setProviderId("");
    setBaseUrl("");
    setApiKey("");
    setModelName("");
    setHeaderRows([]);
    setEnabled(true);
    setTestResult(null);
  }

  function switchMode(next: LlmConfigMode) {
    if (next === mode) {
      return;
    }
    setMode(next);
    clearTestResult();
  }

  const resolvedProviderId =
    mode === "custom" ? sanitizeProviderSlug(providerId) : providerId.trim();

  const payload: LlmCreatePayload = {
    name: configName.trim(),
    mode,
    provider_id: resolvedProviderId,
    base_url: baseUrl.trim() || null,
    api_key: apiKey,
    headers: mode === "custom" ? rowsToHeaders(headerRows) : null,
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
    configName.trim()
      && resolvedProviderId
      && apiKey
      && modelName.trim()
      && (mode === "catalog" || baseUrl.trim()),
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
      <div className="field-label compact">
        provider 来源
        <div
          aria-label="provider 来源"
          className="opencode-segmented llm-mode-segmented"
          role="radiogroup"
        >
          <button
            aria-checked={mode === "catalog"}
            data-tone="whitelist"
            onClick={() => switchMode("catalog")}
            role="radio"
            type="button"
          >
            目录 provider
          </button>
          <button
            aria-checked={mode === "custom"}
            data-tone="whitelist"
            onClick={() => switchMode("custom")}
            role="radio"
            type="button"
          >
            自建网关
          </button>
        </div>
      </div>
      <datalist id={datalistId}>
        {providerOptions.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </datalist>
      <div className="form-row">
        {mode === "catalog" ? (
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
        ) : (
          <label className="field-label compact">
            provider 标识
            <Input
              aria-label="provider 标识"
              className="console-mono"
              onChange={(event) => {
                setProviderId(event.target.value);
                clearTestResult();
              }}
              placeholder="my-gateway"
              value={providerId}
            />
            <span className="field-hint">
              小写字母 / 数字 / - / _，作为 opencode provider key
            </span>
          </label>
        )}
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
        {mode === "custom" ? <span className="field-required">*</span> : null}
        {mode === "catalog" ? (
          <span className="field-hint">可选 · 留空走目录默认端点</span>
        ) : null}
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
      {mode === "custom" ? (
        <div className="field-label compact">
          请求头
          <span className="field-hint">
            自建网关 / 中转站固定走 @ai-sdk/openai-compatible，可附加鉴权头
          </span>
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
      ) : null}
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
              ? `连接正常${testResult.provider_id ? ` · ${testResult.provider_id}` : ""}`
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
