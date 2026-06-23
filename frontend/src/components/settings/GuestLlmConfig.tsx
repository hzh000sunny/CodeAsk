import { useState } from "react";
import { KeyRound, Plus, Trash2, X } from "lucide-react";

import {
  clearGuestLlmConfig,
  getGuestLlmConfig,
  type GuestLlmConfig as GuestLlmConfigValue,
  setGuestLlmConfig,
} from "../../lib/identity";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { sanitizeProviderSlug } from "./settings-utils";

const DEFAULT_GUEST_LLM_CONFIG: GuestLlmConfigValue = {
  name: "访客 LLM",
  mode: "catalog",
  provider_id: "",
  base_url: null,
  api_key: "",
  headers: null,
  model_name: "",
  reasoning_profile: "none",
  reasoning_profile_json: null,
};

interface HeaderRow {
  key: string;
  value: string;
}

function headersToRows(headers: Record<string, string> | null): HeaderRow[] {
  return headers
    ? Object.entries(headers).map(([key, value]) => ({ key, value }))
    : [];
}

function rowsToHeaders(rows: HeaderRow[]): Record<string, string> | null {
  const entries = rows
    .map((row) => [row.key.trim(), row.value] as const)
    .filter(([key]) => key);
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

export function GuestLlmConfig() {
  const { showSuccess } = useAppFeedback();
  const stored = getGuestLlmConfig() ?? DEFAULT_GUEST_LLM_CONFIG;
  const [config, setConfig] = useState<GuestLlmConfigValue>(stored);
  const [headerRows, setHeaderRows] = useState<HeaderRow[]>(
    headersToRows(stored.headers),
  );

  function update<K extends keyof GuestLlmConfigValue>(
    key: K,
    value: GuestLlmConfigValue[K],
  ) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  function save() {
    const mode = config.mode;
    const providerId =
      mode === "custom"
        ? sanitizeProviderSlug(config.provider_id)
        : config.provider_id.trim();
    setGuestLlmConfig({
      ...config,
      provider_id: providerId,
      base_url: config.base_url?.trim() || null,
      headers: mode === "custom" ? rowsToHeaders(headerRows) : null,
    });
    showSuccess("访客 LLM 配置已保存");
  }

  return (
    <section className="surface">
      <div className="section-title">
        <KeyRound aria-hidden="true" size={18} />
        <h2>访客 LLM 配置</h2>
      </div>
      <div className="guest-llm-grid">
        <label className="field-label compact" htmlFor="guest-llm-name">
          配置名称
          <Input
            id="guest-llm-name"
            onChange={(event) => update("name", event.target.value)}
            value={config.name}
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
              aria-checked={config.mode === "catalog"}
              data-tone="whitelist"
              onClick={() => update("mode", "catalog")}
              role="radio"
              type="button"
            >
              目录 provider
            </button>
            <button
              aria-checked={config.mode === "custom"}
              data-tone="whitelist"
              onClick={() => update("mode", "custom")}
              role="radio"
              type="button"
            >
              自建网关
            </button>
          </div>
        </div>
        <label className="field-label compact" htmlFor="guest-llm-provider">
          {config.mode === "custom" ? "provider 标识" : "provider"}
          <Input
            className="console-mono"
            id="guest-llm-provider"
            onChange={(event) => update("provider_id", event.target.value)}
            placeholder={config.mode === "custom" ? "my-gateway" : "deepseek / openai …"}
            value={config.provider_id}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-model">
          模型名称
          <Input
            className="console-mono"
            id="guest-llm-model"
            onChange={(event) => update("model_name", event.target.value)}
            value={config.model_name}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-base-url">
          Base URL
          {config.mode === "custom" ? <span className="field-required">*</span> : null}
          <Input
            className="console-mono"
            id="guest-llm-base-url"
            onChange={(event) => update("base_url", event.target.value)}
            placeholder="https://..."
            value={config.base_url ?? ""}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-api-key">
          API Key
          <Input
            className="console-mono"
            id="guest-llm-api-key"
            onChange={(event) => update("api_key", event.target.value)}
            type="password"
            value={config.api_key}
          />
        </label>
      </div>
      {config.mode === "custom" ? (
        <div className="field-label compact guest-llm-headers">
          请求头
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
                  }}
                  placeholder="value"
                  value={row.value}
                />
                <button
                  aria-label={`删除请求头 ${index + 1}`}
                  className="kv-remove"
                  onClick={() => setHeaderRows(headerRows.filter((_, i) => i !== index))}
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
      <div className="form-actions guest-llm-actions">
        <Button onClick={save} type="button" variant="primary">
          保存访客配置
        </Button>
        <Button
          icon={<Trash2 size={15} />}
          onClick={() => {
            clearGuestLlmConfig();
            setConfig(DEFAULT_GUEST_LLM_CONFIG);
            setHeaderRows([]);
            showSuccess("访客 LLM 配置已清除");
          }}
          type="button"
          variant="quiet"
        >
          清除
        </Button>
      </div>
    </section>
  );
}
