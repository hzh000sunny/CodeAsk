import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { refreshSessionListAfterTitleGeneration } from "../src/components/session/useSessionMessageStream";
import type { SessionResponse } from "../src/types/api";

describe("session title refresh", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("refreshes the session list immediately and again while title generation may still be running", async () => {
    vi.useFakeTimers();
    const queryClient = new QueryClient();
    const invalidate = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue();

    refreshSessionListAfterTitleGeneration(queryClient);

    expect(invalidate).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenLastCalledWith({ queryKey: ["sessions"] });

    await vi.advanceTimersByTimeAsync(1_499);
    expect(invalidate).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(1);
    expect(invalidate).toHaveBeenCalledTimes(2);

    await vi.advanceTimersByTimeAsync(3_500);
    expect(invalidate).toHaveBeenCalledTimes(3);

    await vi.advanceTimersByTimeAsync(7_000);
    expect(invalidate).toHaveBeenCalledTimes(4);
    expect(invalidate).toHaveBeenLastCalledWith({ queryKey: ["sessions"] });
  });

  it("applies the explicitly generated title response to the visible session cache", async () => {
    vi.useFakeTimers();
    const queryClient = new QueryClient();
    const defaultSession = session({
      id: "sess_title",
      title: "新的研发会话",
      title_source: "default",
    });
    const generatedSession = session({
      id: "sess_title",
      title: "CodeAsk 能力介绍",
      title_source: "auto",
    });
    const rememberSession = vi.fn();
    const generateSessionTitle = vi.fn().mockResolvedValue(generatedSession);
    queryClient.setQueryData(["sessions", "auth:admin"], [defaultSession]);
    vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue();

    refreshSessionListAfterTitleGeneration(queryClient, {
      sessionId: "sess_title",
      rememberSession,
      generateSessionTitle,
    });
    await vi.runOnlyPendingTimersAsync();

    expect(generateSessionTitle).toHaveBeenCalledWith("sess_title");
    expect(rememberSession).toHaveBeenCalledWith(generatedSession);
  });
});

function session(overrides: Partial<SessionResponse>): SessionResponse {
  return {
    id: "sess_1",
    title: "新的研发会话",
    created_by_subject_id: "admin",
    status: "active",
    pinned: false,
    title_source: "default",
    title_generated_at: null,
    created_at: "2026-05-09T05:00:00",
    updated_at: "2026-05-09T05:00:00",
    ...overrides,
  };
}
