import { describe, expect, it } from "vitest";

import { createInitialStages } from "../src/components/session/session-model";

describe("session runtime stage model", () => {
  it("orders knowledge retrieval before evidence sufficiency and code investigation", () => {
    const stages = createInitialStages();
    const keys = stages.map((stage) => stage.key);

    expect(keys).toEqual([
      "input_analysis",
      "scope_detection",
      "knowledge_retrieval",
      "sufficiency_judgement",
      "code_investigation",
      "answer_finalization",
    ]);
    expect(
      stages.find((stage) => stage.key === "scope_detection")?.detail,
    ).toBe("识别问题关联的特性和上下文范围");
    expect(
      stages.find((stage) => stage.key === "sufficiency_judgement")?.detail,
    ).toBe("判断知识证据是否足够回答");
  });
});
