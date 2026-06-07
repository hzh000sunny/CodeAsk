import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { MarkdownRenderer } from "../../src/components/ui/MarkdownRenderer";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async (id: string) => ({
      svg: `<svg data-testid="mock-mermaid-svg" data-id="${id}" viewBox="0 0 1800 900"><text>流程图</text></svg>`,
    })),
  },
}));

describe("MarkdownRenderer wiki affordances", () => {
  it("maps internal markdown links to wiki hash routes", () => {
    render(
      <MarkdownRenderer
        content="[Jump](./target-doc.md)"
        linkHrefMap={{ "./target-doc.md": "#/wiki?feature=7&node=25" }}
      />,
    );

    expect(screen.getByRole("link", { name: "Jump" })).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=25",
    );
  });

  it("keeps direct wiki hash links clickable for session answers", () => {
    render(
      <MarkdownRenderer content="[查看知识库](#/wiki?feature=7&node=25)" />,
    );

    expect(screen.getByRole("link", { name: "查看知识库" })).toHaveAttribute(
      "href",
      "#/wiki?feature=7&node=25",
    );
  });

  it("renders mapped relative image assets with native wiki content urls", () => {
    render(
      <MarkdownRenderer
        content="![Diagram](./diagram.png)"
        imageSrcMap={{ "./diagram.png": "/api/wiki/assets/88/content" }}
      />,
    );

    expect(screen.getByRole("img", { name: "Diagram" })).toHaveAttribute(
      "src",
      "/api/wiki/assets/88/content",
    );
  });

  it("resolves chinese relative image paths despite react-markdown url encoding", () => {
    // react-markdown 会把含中文的相对路径百分号编码后传给 img；查表需按解码后命中。
    render(
      <MarkdownRenderer
        content="![中文图](图片/测试.png)"
        imageSrcMap={{ "图片/测试.png": "/api/wiki/assets/91/content" }}
      />,
    );

    expect(screen.getByRole("img", { name: "中文图" })).toHaveAttribute(
      "src",
      "/api/wiki/assets/91/content",
    );
  });

  it("renders external http(s) image urls directly even if legacy resolution marked them broken", () => {
    render(
      <MarkdownRenderer
        brokenImageTargets={new Set(["https://example.com/a.png"])}
        content="![远程](https://example.com/a.png)"
      />,
    );

    expect(screen.getByRole("img", { name: "远程" })).toHaveAttribute(
      "src",
      "https://example.com/a.png",
    );
    expect(screen.queryByText("图片无法加载")).not.toBeInTheDocument();
  });

  it("renders mapped html img assets with native wiki content urls", () => {
    render(
      <MarkdownRenderer
        content={'<img src="Untitled.assets/image-1.png" alt="病例截图" style="zoom:50%;" />'}
        imageSrcMap={{ "Untitled.assets/image-1.png": "/api/wiki/assets/108/content" }}
      />,
    );

    expect(screen.getByRole("img", { name: "病例截图" })).toHaveAttribute(
      "src",
      "/api/wiki/assets/108/content",
    );
  });

  it("shows visible feedback for broken relative images", () => {
    render(
      <MarkdownRenderer
        brokenImageTargets={new Set(["./missing.png"])}
        content="![Broken](./missing.png)"
      />,
    );

    expect(screen.getByText("图片无法加载")).toBeInTheDocument();
    expect(screen.getByText("./missing.png")).toBeInTheDocument();
  });

  it("falls back to a placeholder when an image load fails at runtime", () => {
    render(<MarkdownRenderer content="![Broken](./later-missing.png)" />);

    fireEvent.error(screen.getByRole("img", { name: "Broken" }));

    expect(screen.getByText("图片无法加载")).toBeInTheDocument();
    expect(screen.getByText("./later-missing.png")).toBeInTheDocument();
  });

  it("renders mermaid flowcharts as diagrams instead of plain code blocks", async () => {
    render(
      <MarkdownRenderer
        content={[
          "# 主备重建流程",
          "",
          "```mermaid",
          "flowchart TD",
          "  A[开始] --> B{是否全量 build}",
          "  B -- 是 --> C[全量 build]",
          "  B -- 否 --> D[增量 build]",
          "  C --> E[拉起数据库进程]",
          "  D --> E",
          "```",
        ].join("\n")}
      />,
    );

    expect(await screen.findByTestId("mock-mermaid-svg")).toBeInTheDocument();
    expect(
      document.querySelector<HTMLElement>(".markdown-mermaid-svg"),
    ).toHaveStyle({ minWidth: "1200px" });
    expect(screen.queryByRole("button", { name: "复制代码块" })).not.toBeInTheDocument();
  });
});
