import { describe, expect, it } from "vitest";

import {
  REPORT_PREPARE_TIMEOUT_MS,
  reportPreparePollingDelayMs,
} from "../src/components/session/useSessionReport";

describe("session report prepare polling", () => {
  it("polls quickly at first and backs off after thirty seconds", () => {
    expect(reportPreparePollingDelayMs(0)).toBe(2_000);
    expect(reportPreparePollingDelayMs(29_999)).toBe(2_000);
    expect(reportPreparePollingDelayMs(30_000)).toBe(5_000);
    expect(reportPreparePollingDelayMs(120_000)).toBe(5_000);
  });

  it("keeps the report prepare timeout at ten minutes", () => {
    expect(REPORT_PREPARE_TIMEOUT_MS).toBe(600_000);
  });
});
