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
      mode: "catalog",
      provider_id: "  deepseek  ",
      base_url: "  http://localhost:8001/v1  ",
      api_key: "  sk-test  ",
      headers: null,
      model_name: "  glm-test  ",
      reasoning_profile: "none",
      reasoning_profile_json: "",
    });

    expect(getGuestLlmConfig()).toEqual({
      name: "Local GLM",
      mode: "catalog",
      provider_id: "deepseek",
      base_url: "http://localhost:8001/v1",
      api_key: "sk-test",
      headers: null,
      model_name: "glm-test",
      reasoning_profile: "none",
      reasoning_profile_json: null,
    });
  });

  it("keeps custom-mode headers and drops blank-keyed entries", () => {
    setGuestLlmConfig({
      name: "gateway",
      mode: "custom",
      provider_id: "my-gateway",
      base_url: "https://relay.example.test",
      api_key: "sk",
      headers: { Authorization: "Bearer x", "": "ignored" },
      model_name: "model",
      reasoning_profile: "none",
      reasoning_profile_json: null,
    });

    expect(getGuestLlmConfig()?.headers).toEqual({ Authorization: "Bearer x" });
  });

  it("clears invalid or removed guest config", () => {
    localStorage.setItem("codeask.guest_llm_config", "{broken");
    expect(getGuestLlmConfig()).toBeNull();

    setGuestLlmConfig({
      name: "x",
      mode: "catalog",
      provider_id: "anthropic",
      base_url: null,
      api_key: "sk",
      headers: null,
      model_name: "claude",
      reasoning_profile: "none",
      reasoning_profile_json: null,
    });
    clearGuestLlmConfig();

    expect(getGuestLlmConfig()).toBeNull();
  });
});
