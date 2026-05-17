import { describe, expect, it } from "vitest";

import {
  clearGuestLlmConfig,
  getGuestLlmConfig,
  setGuestLlmConfig,
} from "../src/lib/identity";

describe("guest llm config storage", () => {
  it("stores a sanitized browser-local LLM config", () => {
    setGuestLlmConfig({
      name: "  Local GLM  ",
      protocol: "openai",
      base_url: "  http://localhost:8001/v1  ",
      api_key: "  sk-test  ",
      model_name: "  glm-test  ",
      max_tokens: 4096,
      temperature: 0.2,
      reasoning_profile: "none",
      reasoning_profile_json: "",
      agent_runtime_profile: "openai-compatible",
    });

    expect(getGuestLlmConfig()).toEqual({
      name: "Local GLM",
      protocol: "openai",
      base_url: "http://localhost:8001/v1",
      api_key: "sk-test",
      model_name: "glm-test",
      max_tokens: 4096,
      temperature: 0.2,
      reasoning_profile: "none",
      reasoning_profile_json: null,
      agent_runtime_profile: "openai-compatible",
    });
  });

  it("clears invalid or removed guest config", () => {
    localStorage.setItem("codeask.guest_llm_config", "{broken");
    expect(getGuestLlmConfig()).toBeNull();

    setGuestLlmConfig({
      name: "x",
      protocol: "anthropic",
      base_url: null,
      api_key: "sk",
      model_name: "claude",
      max_tokens: 1024,
      temperature: 0,
      reasoning_profile: "none",
      reasoning_profile_json: null,
      agent_runtime_profile: "default",
    });
    clearGuestLlmConfig();

    expect(getGuestLlmConfig()).toBeNull();
  });

  it("migrates legacy opencode guest runtime profile to the generic field", () => {
    localStorage.setItem(
      "codeask.guest_llm_config",
      JSON.stringify({
        name: "legacy",
        protocol: "openai",
        api_key: "sk",
        model_name: "model",
        opencode_provider_profile: "openai-compatible",
      }),
    );

    expect(getGuestLlmConfig()).toMatchObject({
      agent_runtime_profile: "openai-compatible",
    });
  });
});
