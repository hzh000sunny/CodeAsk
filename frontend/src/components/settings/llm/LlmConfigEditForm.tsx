import { useState } from "react";
import type { FormEvent } from "react";

import type { LLMConfigResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type {
  LlmProtocol,
  LlmReasoningProfile,
  LlmUpdatePayload,
} from "../settings-types";
import { safeEditableProtocol } from "../settings-utils";

export function LlmConfigEditForm({
  config,
  disabled,
  onCancel,
  onSubmit,
}: {
  config: LLMConfigResponse;
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (payload: LlmUpdatePayload) => void;
}) {
  const [name, setName] = useState(config.name);
  const [protocol, setProtocol] = useState<LlmProtocol>(
    safeEditableProtocol(config.protocol),
  );
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState(config.model_name);
  const [reasoningProfile, setReasoningProfile] =
    useState<LlmReasoningProfile>(
      (config.reasoning_profile as LlmReasoningProfile) || "none",
    );
  const [reasoningProfileJson, setReasoningProfileJson] = useState(
    config.reasoning_profile_json ?? "",
  );

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: LlmUpdatePayload = {
      name: name.trim(),
      protocol,
      base_url: baseUrl.trim() || null,
      model_name: modelName.trim(),
      reasoning_profile: reasoningProfile,
      reasoning_profile_json:
        reasoningProfile === "custom_json"
          ? reasoningProfileJson.trim() || null
          : null,
    };
    if (apiKey) {
      payload.api_key = apiKey;
    }
    onSubmit(payload);
  }

  return (
    <form className="inline-form llm-form llm-edit-form" onSubmit={submit}>
      <label className="field-label compact">
        编辑配置名称
        <Input onChange={(event) => setName(event.target.value)} value={name} />
      </label>
      <label className="field-label compact">
        编辑消息接口协议
        <select
          className="input"
          onChange={(event) => setProtocol(event.target.value as LlmProtocol)}
          value={protocol}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </label>
      <label className="field-label compact">
        编辑 Base URL
        <Input
          onChange={(event) => setBaseUrl(event.target.value)}
          value={baseUrl}
        />
      </label>
      <label className="field-label compact">
        编辑 API Key
        <Input
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="留空则不修改"
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        编辑模型名称
        <Input
          onChange={(event) => setModelName(event.target.value)}
          value={modelName}
        />
      </label>
      <label className="field-label compact">
        编辑 Reasoning 请求 Profile
        <select
          className="input"
          onChange={(event) =>
            setReasoningProfile(event.target.value as LlmReasoningProfile)
          }
          value={reasoningProfile}
        >
          <option value="none">不额外开启</option>
          <option value="volcengine_thinking">火山 Thinking</option>
          <option value="vllm_enable_thinking">vLLM enable_thinking</option>
          <option value="anthropic_budget_thinking">Anthropic budget thinking</option>
          <option value="custom_json">自定义 JSON</option>
        </select>
      </label>
      {reasoningProfile === "custom_json" ? (
        <label className="field-label compact">
          编辑 Profile JSON
          <Input
            onChange={(event) => setReasoningProfileJson(event.target.value)}
            placeholder='{"extra_body":{"include_reasoning":true}}'
            value={reasoningProfileJson}
          />
        </label>
      ) : null}
      <div className="form-actions llm-edit-actions">
        <Button
          disabled={!name.trim() || !modelName.trim() || disabled}
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
