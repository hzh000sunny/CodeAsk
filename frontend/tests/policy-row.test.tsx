import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { PolicyRow } from "../src/components/policies/PolicyRow";
import type { SkillResponse } from "../src/types/api";

function policy(overrides: Partial<SkillResponse> = {}): SkillResponse {
  return {
    enabled: true,
    feature_id: 1,
    id: "policy-build",
    name: "build分析策略",
    priority: 100,
    prompt_template:
      "全流程 · 优先级 100 · 你负责主备重建特性的咨询和问题定位。遇到 build、全量 build、增量 build、主备重建相关问题时，必须先读取 Wiki。阅读顺序为 index 全局索引、全量 build 文档、增量 build 文档和其它相关文档。咨询类问题先通过 Wiki 判断是否能够回答，无法回答时需要询问用户是否查询代码；问题定位类问题先要求用户提供客户端日志，从日志判断是 build 失败，还是 build 成功后数据库进程拉起失败。",
    scope: "feature",
    stage: "all",
    ...overrides,
  };
}

describe("PolicyRow", () => {
  test("renders long policy prompts as a readable preview with expandable full text", () => {
    const { container } = render(
      <ul>
        <PolicyRow
          editing={false}
          onCancel={vi.fn()}
          onDelete={vi.fn()}
          onEdit={vi.fn()}
          onSubmit={vi.fn()}
          onToggle={vi.fn()}
          pending={false}
          policy={policy()}
        />
      </ul>,
    );

    expect(screen.getByText("build分析策略")).toBeInTheDocument();
    expect(screen.getByText("全流程 · 优先级 100")).toBeInTheDocument();
    expect(container.querySelector(".policy-prompt-preview")).not.toBeNull();
    expect(
      screen.getByRole("button", { name: "查看完整策略" }),
    ).toBeInTheDocument();
    expect(container.querySelector(".policy-full-text")).not.toBeNull();
  });
});
