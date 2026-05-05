import { describe, expect, it } from "vitest";

import {
  createInitialStages,
  runtimeInsightFromEvent,
} from "../src/components/session/session-model";

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

  it("maps wiki scope resolution events into readable runtime insights", () => {
    const insight = runtimeInsightFromEvent({
      type: "wiki_scope_resolution",
      data: {
        query: "支付回调超时",
        defaults: [
          { node_id: 2, path: "知识库", label: "知识库" },
          { node_id: 3, path: "问题定位报告", label: "问题定位报告" },
        ],
        matches: [
          {
            node_id: 10,
            path: "知识库/支付回调",
            label: "支付回调",
            match_reason: "contains",
            matched_phrase: "支付回调",
          },
        ],
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("wiki_scope");
    expect(insight?.title).toContain("Wiki 范围");
    expect(insight?.detail).toContain("显式命中 1 个节点");
    expect(insight?.detailMarkdown).toContain("知识库/支付回调");
    expect(insight?.detailMarkdown).toContain("**默认范围**");
  });

  it("uses per-item feature ids when rendering cross-feature wiki scope links", () => {
    const insight = runtimeInsightFromEvent({
      type: "wiki_scope_resolution",
      data: {
        feature_id: 1,
        feature_ids: [1, 2],
        query: "跨特性回调超时",
        defaults: [
          { feature_id: 1, node_id: 2, path: "知识库", label: "知识库" },
          { feature_id: 2, node_id: 12, path: "知识库", label: "知识库" },
        ],
        matches: [
          {
            feature_id: 2,
            node_id: 18,
            path: "知识库/支付回调",
            label: "支付回调",
            match_reason: "contains",
            matched_phrase: "支付回调",
          },
        ],
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.detailMarkdown).toContain("#/wiki?feature=2&node=18");
  });

  it("maps wiki evidence events into clickable markdown details with heading targets", () => {
    const insight = runtimeInsightFromEvent({
      type: "evidence",
      data: {
        item: {
          id: "ev_knowledge_1",
          title: "回调 Runbook",
          source: "doc",
          path: "知识库/回调 Runbook",
          heading_path: "回调 Runbook > 排查步骤",
          feature_id: 7,
          node_id: 15,
        },
      },
    });

    expect(insight).not.toBeNull();
    expect(insight?.kind).toBe("evidence");
    expect(insight?.detail).toContain("回调 Runbook > 排查步骤");
    expect(insight?.detailMarkdown).toContain("#/wiki?feature=7&node=15");
    expect(insight?.detailMarkdown).toContain("heading=%E5%9B%9E%E8%B0%83+Runbook+%3E+%E6%8E%92%E6%9F%A5%E6%AD%A5%E9%AA%A4");
  });
});
