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
    });
    clearGuestLlmConfig();

    expect(getGuestLlmConfig()).toBeNull();
  });
});
