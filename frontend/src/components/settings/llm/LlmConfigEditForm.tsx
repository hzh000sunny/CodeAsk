import { useState } from "react";
import type { FormEvent } from "react";

import type { LLMConfigResponse } from "../../../types/api";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import type { LlmProtocol, LlmUpdatePayload } from "../settings-types";
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

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: LlmUpdatePayload = {
      name: name.trim(),
      protocol,
      base_url: baseUrl.trim() || null,
      model_name: modelName.trim(),
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
