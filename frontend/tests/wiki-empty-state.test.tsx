import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WikiEmptyState } from "../src/components/wiki/WikiEmptyState";

describe("WikiEmptyState", () => {
  it("renders a guided empty state for feature knowledge bases", () => {
    const onCreateDocument = vi.fn();
    const onImport = vi.fn();

    render(
      <WikiEmptyState
        canCreate
        description="当前特性还没有 Wiki 文档，或当前选择的节点不是文档。"
        mode="feature"
        onCreateDocument={onCreateDocument}
        onImport={onImport}
        title="开始建设这个特性的 Wiki"
      />,
    );

    expect(screen.getByText("开始建设这个特性的 Wiki")).toBeInTheDocument();
    expect(screen.getByText("新建空白 Wiki")).toBeInTheDocument();
    expect(screen.getByText("导入现有资料")).toBeInTheDocument();
    expect(screen.getByText("支持 Markdown")).toBeInTheDocument();
    expect(screen.getByText("导入后自动索引")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新建 Wiki" }));
    fireEvent.click(screen.getByRole("button", { name: "导入 Wiki" }));

    expect(onCreateDocument).toHaveBeenCalledTimes(1);
    expect(onImport).toHaveBeenCalledTimes(1);
  });
});
