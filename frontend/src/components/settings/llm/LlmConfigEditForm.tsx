import { useId, useState } from "react";
import type { FormEvent } from "react";
import { AlertTriangle, Check, PlugZap, Plus, X } from "lucide-react";

import type { LLMConfigResponse, LLMConfigTestResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type {
  LlmConfigMode,
  LlmProviderOption,
  LlmUpdatePayload,
} from "../settings-types";
import { sanitizeProviderSlug } from "../settings-utils";

interface HeaderRow {
  key: string;
  value: string;
}

export function LlmConfigEditForm({
  config,
  disabled,
  onCancel,
  onTest,
  onSubmit,
  providerOptions = [],
  testing,
}: {
  config: LLMConfigResponse;
  disabled: boolean;
  onCancel: () => void;
  onTest: (payload: LlmUpdatePayload) => Promise<LLMConfigTestResponse>;
  onSubmit: (payload: LlmUpdatePayload) => void;
  providerOptions?: LlmProviderOption[];
  testing: boolean;
}) {
  const datalistId = useId();
  const initialMode: LlmConfigMode = config.mode === "custom" ? "custom" : "catalog";
  const [name, setName] = useState(config.name);
  const [mode, setMode] = useState<LlmConfigMode>(initialMode);
  const [providerId, setProviderId] = useState(config.provider_id);
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState(config.model_name);
  const [replacingHeaders, setReplacingHeaders] = useState(false);
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>([]);
  const [testResult, setTestResult] = useState<LLMConfigTestResponse | null>(null);

  const existingHeaderKeys = Object.keys(config.headers_masked ?? {});

  function clearTestResult() {
    setTestResult(null);
  }

  function switchMode(next: LlmConfigMode) {
    if (next === mode) {
      return;
    }
    setMode(next);
    clearTestResult();
  }

  function beginHeaderReplace() {
    setReplacingHeaders(true);
    setHeaderRows(
      existingHeaderKeys.length > 0
        ? existingHeaderKeys.map((key) => ({ key, value: "" }))
        : [{ key: "", value: "" }],
    );
    clearTestResult();
  }

  const resolvedProviderId =
    mode === "custom" ? sanitizeProviderSlug(providerId) : providerId.trim();
  const normalizedBaseUrl = baseUrl.trim() || null;

  const payload: LlmUpdatePayload = {};
  if (name.trim() !== config.name) {
    payload.name = name.trim();
  }
  if (mode !== config.mode) {
    payload.mode = mode;
  }
  if (resolvedProviderId !== config.provider_id) {
    payload.provider_id = resolvedProviderId;
  }
  if (normalizedBaseUrl !== config.base_url) {
    payload.base_url = normalizedBaseUrl;
  }
  if (modelName.trim() !== config.model_name) {
    payload.model_name = modelName.trim();
  }
  if (apiKey) {
    payload.api_key = apiKey;
  }
  if (replacingHeaders) {
    const entries = headerRows
      .map((row) => [row.key.trim(), row.value] as const)
      .filter(([key]) => key);
    payload.headers = entries.length > 0 ? Object.fromEntries(entries) : {};
  }
  if (testResult) {
    payload.opencode_provider_status = testResult.status;
    payload.opencode_provider_tested_at = testResult.tested_at;
    payload.opencode_provider_error = testResult.error;
    payload.opencode_provider_test_result_json = testResult.result;
  }
  const canSubmit = Boolean(
    name.trim()
      && resolvedProviderId
      && modelName.trim()
      && (mode === "catalog" || normalizedBaseUrl),
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
              value={providerId}
            />
            <span className="field-hint">
              小写字母 / 数字 / - / _，作为 opencode provider key
            </span>
          </label>
        )}
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
        {mode === "custom" ? <span className="field-required">*</span> : null}
        {mode === "catalog" ? (
          <span className="field-hint">可选 · 留空走目录默认端点</span>
        ) : null}
        <Input
          aria-label="编辑 Base URL"
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
      {mode === "custom" ? (
        <div className="field-label compact">
          请求头
          {replacingHeaders ? (
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
          ) : (
            <div className="kv-readonly">
              <span className="field-hint">
                {existingHeaderKeys.length > 0
                  ? `已配置 ${existingHeaderKeys.length} 个请求头（值已脱敏）`
                  : "未配置自定义请求头"}
              </span>
              <button
                className="kv-add"
                onClick={beginHeaderReplace}
                type="button"
              >
                重设请求头
              </button>
            </div>
          )}
        </div>
      ) : null}
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
