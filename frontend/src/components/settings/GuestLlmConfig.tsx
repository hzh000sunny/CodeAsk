import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2, X } from "lucide-react";

import { listLlmProviders } from "../../lib/api";
import {
  clearGuestLlmConfig,
  getGuestLlmConfig,
  type GuestLlmConfig as GuestLlmConfigValue,
  setGuestLlmConfig,
} from "../../lib/identity";
import { useAppFeedback } from "../feedback/AppFeedback";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

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
  const providerListId = useId();
  const { data: providers } = useQuery({
    queryKey: ["llm-providers"],
    queryFn: listLlmProviders,
    staleTime: 5 * 60 * 1000,
  });
  const providerOptions = providers?.providers ?? [];
  const stored = getGuestLlmConfig() ?? DEFAULT_GUEST_LLM_CONFIG;
  const [config, setConfig] = useState<GuestLlmConfigValue>(stored);
  const [showHeaders, setShowHeaders] = useState(
    Boolean(stored.headers && Object.keys(stored.headers).length > 0),
  );
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
    setGuestLlmConfig({
      ...config,
      mode: "catalog",
      provider_id: config.provider_id.trim(),
      base_url: config.base_url?.trim() || null,
      headers: showHeaders ? rowsToHeaders(headerRows) : null,
    });
    showSuccess("访客 LLM 配置已保存");
  }

  return (
    <section className="surface">
      <div className="section-title">
        <KeyRound aria-hidden="true" size={18} />
        <h2>访客 LLM 配置</h2>
      </div>
      <p className="guest-llm-lede">
        填入你自己的模型账号即可开始对话；密钥仅保存在此浏览器，不会上传服务器。
      </p>
      <div className="guest-llm-grid">
        <label className="field-label compact" htmlFor="guest-llm-name">
          配置名称
          <Input
            id="guest-llm-name"
            onChange={(event) => update("name", event.target.value)}
            value={config.name}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-provider">
          provider
          <Input
            className="console-mono"
            id="guest-llm-provider"
            list={providerListId}
            onChange={(event) => update("provider_id", event.target.value)}
            placeholder="deepseek / openai …"
            value={config.provider_id}
          />
          <datalist id={providerListId}>
            {providerOptions.map((option) => (
              <option key={option.id} value={option.id} />
            ))}
          </datalist>
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
          <Input
            className="console-mono"
            id="guest-llm-base-url"
            onChange={(event) => update("base_url", event.target.value)}
            placeholder="https://...（可选，填入即作为网关地址）"
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
      {showHeaders ? (
        <div className="field-label compact guest-llm-headers">
          自定义请求头
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
      <div className="form-actions guest-llm-actions">
        <Button onClick={save} type="button" variant="primary">
          保存访客配置
        </Button>
        <Button
          icon={<Trash2 size={15} />}
          onClick={() => {
            clearGuestLlmConfig();
            setConfig(DEFAULT_GUEST_LLM_CONFIG);
            setShowHeaders(false);
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
