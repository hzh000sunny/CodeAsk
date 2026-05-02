import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("CodeAsk AppShell information architecture", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse({
            subject_id: "client_test",
            display_name: "client_test",
            role: "member",
            authenticated: false,
          });
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/features") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        return jsonResponse({});
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("keeps the primary navigation to sessions, features, and settings", () => {
    render(<App />);

    const navigation = screen.getByRole("navigation", { name: "主导航" });
    expect(
      within(navigation).getByRole("button", { name: "会话" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "特性" }),
    ).toBeInTheDocument();
    expect(
      within(navigation).getByRole("button", { name: "设置" }),
    ).toBeInTheDocument();
    expect(within(navigation).queryByText("Wiki")).not.toBeInTheDocument();
    expect(within(navigation).queryByText("全局配置")).not.toBeInTheDocument();
  });

  it("allows primary and secondary sidebars to collapse and expand", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "收起主导航" }));
    expect(
      screen.getByRole("button", { name: "展开主导航" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "收起会话列表" }));
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开会话列表" }));
    expect(screen.getByPlaceholderText("搜索会话")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    fireEvent.click(screen.getByRole("button", { name: "收起特性列表" }));
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开特性列表" }));
    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    fireEvent.click(screen.getByRole("button", { name: "收起设置导航" }));
    expect(
      screen.queryByRole("button", { name: "用户设置" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "展开设置导航" }));
    expect(
      await screen.findByRole("button", { name: "用户设置" }),
    ).toBeInTheDocument();
  });

  it("shows the session workspace as a three-column page with search, create, and progress", () => {
    render(<App />);

    expect(screen.getByPlaceholderText("搜索会话")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新建会话" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("我的会话")).not.toBeInTheDocument();
    expect(screen.queryByText("全部会话")).not.toBeInTheDocument();

    expect(
      screen.getByRole("region", { name: "会话列表" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "会话消息" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "调查进度" }),
    ).toBeInTheDocument();
  });

  it("opens the feature workbench with list search, create, and same-page detail tabs", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));

    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "添加特性" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "设置" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("tab", { name: "知识库" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "问题报告" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "关联仓库" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "特性分析策略" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("#/features");
  });

  it("restores the active primary section from the URL hash after reload", async () => {
    window.history.replaceState(null, "", "/#/settings");

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "用户配置" }),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "设置" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("restores the feature workbench from the URL hash after reload", () => {
    window.history.replaceState(null, "", "/#/features");

    render(<App />);

    expect(screen.getByPlaceholderText("搜索特性")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "特性" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("keeps user settings under settings and hides global configuration for members", async () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(
      await screen.findByRole("heading", { name: "用户配置" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "全局配置" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "全局配置" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索会话")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("搜索特性")).not.toBeInTheDocument();
  });
});
