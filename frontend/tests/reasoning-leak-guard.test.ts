import { describe, expect, it } from "vitest";

import {
  createReasoningLeakGuard,
  visibleContentFromLeakGuardResult,
} from "../src/components/session/reasoning-leak-guard";

describe("reasoning leak guard", () => {
  it("leaves content unchanged when disabled", () => {
    const guard = createReasoningLeakGuard("disabled");

    const result = guard.feed("<think>内部</think>正式回答");

    expect(result.visibleText).toBe("<think>内部</think>正式回答");
    expect(result.diagnostic).toBeNull();
  });

  it("warns without masking content in warn_only mode", () => {
    const guard = createReasoningLeakGuard("warn_only");

    const result = guard.feed("<think>内部</think>正式回答");

    expect(result.visibleText).toBe("<think>内部</think>正式回答");
    expect(result.diagnostic?.type).toBe("reasoning_leak_detected");
    expect(result.diagnostic?.rawText).toBeUndefined();
  });

  it("masks leaked thinking in UI mode without exposing raw diagnostic text", () => {
    const guard = createReasoningLeakGuard("mask_in_ui");

    const result = guard.feed("<think>内部</think>正式回答");

    expect(result.visibleText).toBe("正式回答");
    expect(result.diagnostic).toMatchObject({
      type: "reasoning_leak_detected",
      mode: "mask_in_ui",
      marker: "think",
      leakedLength: 2,
    });
    expect(result.diagnostic?.rawText).toBeUndefined();
  });

  it("handles split think tags across chunks", () => {
    const guard = createReasoningLeakGuard("mask_in_ui");

    const first = guard.feed("前缀<thi");
    const second = guard.feed("nk>内部</th");
    const third = guard.feed("ink>结论");

    expect(
      visibleContentFromLeakGuardResult([first, second, third]),
    ).toBe("前缀结论");
    expect(third.diagnostic?.leakedLength).toBe(2);
  });

  it("masks orphan closing think tags without dropping visible text", () => {
    const guard = createReasoningLeakGuard("mask_in_ui");

    const result = guard.feed("OK</think>继续回答");

    expect(result.visibleText).toBe("OK继续回答");
    expect(result.diagnostic).toMatchObject({
      type: "reasoning_leak_detected",
      mode: "mask_in_ui",
      marker: "think",
      leakedLength: 0,
    });
  });

  it("handles split orphan closing think tags across chunks", () => {
    const guard = createReasoningLeakGuard("mask_in_ui");

    const first = guard.feed("OK</th");
    const second = guard.feed("ink>继续回答");

    expect(visibleContentFromLeakGuardResult([first, second])).toBe("OK继续回答");
    expect(second.diagnostic?.leakedLength).toBe(0);
  });
});
