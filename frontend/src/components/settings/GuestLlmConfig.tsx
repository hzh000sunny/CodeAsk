import { useState } from "react";
import { KeyRound, Trash2 } from "lucide-react";

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
  protocol: "openai",
  base_url: "",
  api_key: "",
  model_name: "",
  max_tokens: 4096,
  temperature: 0,
  reasoning_profile: "none",
  reasoning_profile_json: null,
};

export function GuestLlmConfig() {
  const { showSuccess } = useAppFeedback();
  const [config, setConfig] = useState<GuestLlmConfigValue>(
    () => getGuestLlmConfig() ?? DEFAULT_GUEST_LLM_CONFIG,
  );

  function update<K extends keyof GuestLlmConfigValue>(
    key: K,
    value: GuestLlmConfigValue[K],
  ) {
    setConfig((current) => ({ ...current, [key]: value }));
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
        <label className="field-label compact" htmlFor="guest-llm-protocol">
          协议
          <select
            className="input"
            id="guest-llm-protocol"
            onChange={(event) =>
              update("protocol", event.target.value === "anthropic" ? "anthropic" : "openai")
            }
            value={config.protocol}
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
        <label className="field-label compact" htmlFor="guest-llm-base-url">
          Base URL
          <Input
            id="guest-llm-base-url"
            onChange={(event) => update("base_url", event.target.value)}
            placeholder="https://..."
            value={config.base_url ?? ""}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-model">
          模型名称
          <Input
            id="guest-llm-model"
            onChange={(event) => update("model_name", event.target.value)}
            value={config.model_name}
          />
        </label>
        <label className="field-label compact" htmlFor="guest-llm-api-key">
          API Key
          <Input
            id="guest-llm-api-key"
            onChange={(event) => update("api_key", event.target.value)}
            type="password"
            value={config.api_key}
          />
        </label>
      </div>
      <div className="form-actions guest-llm-actions">
        <Button
          onClick={() => {
            setGuestLlmConfig(config);
            showSuccess("访客 LLM 配置已保存");
          }}
          type="button"
          variant="primary"
        >
          保存访客配置
        </Button>
        <Button
          icon={<Trash2 size={15} />}
          onClick={() => {
            clearGuestLlmConfig();
            setConfig(DEFAULT_GUEST_LLM_CONFIG);
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
