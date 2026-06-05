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

  it("renders a neutral select prompt without build CTAs in select mode", () => {
    render(
      <WikiEmptyState
        canCreate={false}
        description="从左侧目录展开特性，点选其下的文档即可在此阅读。"
        mode="select"
        title="选择一篇 Wiki 查看"
      />,
    );

    expect(screen.getByText("选择一篇 Wiki 查看")).toBeInTheDocument();
    // 引导态不预设特性，也不提供建设入口。
    expect(screen.queryByText(/开始建设/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新建 Wiki" })).not.toBeInTheDocument();
    expect(screen.queryByText("新建空白 Wiki")).not.toBeInTheDocument();
  });
});
