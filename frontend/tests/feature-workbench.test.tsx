import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_test",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00"
};

const existingRepo = {
  id: "repo_existing",
  name: "platform-api",
  source: "local_dir",
  url: null,
  local_path: "/repo/platform-api",
  bare_path: "/tmp/repos/repo_existing/bare",
  status: "ready",
  error_message: null,
  last_synced_at: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00"
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function installFeatureFetchMock(options: { repos?: unknown[] } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/auth/me") {
      return jsonResponse({
        subject_id: "client_test",
        display_name: "client_test",
        role: "member",
        authenticated: false
      });
    }
    if (path === "/api/features" && init?.method !== "POST") {
      return jsonResponse([feature]);
    }
    if (path === "/api/features" && init?.method === "POST") {
      return jsonResponse({ ...feature, id: 8, name: "风控策略", slug: "risk-policy" }, 201);
    }
    if (path === "/api/features/7" && init?.method === "DELETE") {
      return new Response(null, { status: 204 });
    }
    if (path === "/api/documents?feature_id=7") {
      return jsonResponse([]);
    }
    if (path === "/api/documents" && init?.method === "POST") {
      return jsonResponse({
        id: 12,
        feature_id: 7,
        kind: "markdown",
        title: "支付 Wiki",
        path: "payment.md",
        tags_json: null,
        summary: null,
        is_deleted: false,
        uploaded_by_subject_id: "client_test",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00"
      }, 201);
    }
    if (path === "/api/reports?feature_id=7") {
      return jsonResponse([
        {
        id: 21,
        feature_id: 7,
        title: "启动失败复盘",
        body_markdown: "配置缺失导致启动失败",
        metadata_json: {},
        status: "draft",
        verified: false,
        verified_by: null,
        verified_at: null,
        created_by_subject_id: "client_test",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00"
        }
      ]);
    }
    if (path === "/api/repos") {
      if (init?.method === "POST") {
        return jsonResponse({
          id: "repo_1",
          name: "codeask",
          source: "local_dir",
          url: null,
          local_path: "/repo/codeask",
          bare_path: "/tmp/repos/repo_1/bare",
          status: "registered",
          error_message: null,
          last_synced_at: null,
          created_at: "2026-04-30T10:00:00",
          updated_at: "2026-04-30T10:00:00"
        }, 201);
      }
      return jsonResponse({ repos: options.repos ?? [] });
    }
    if (path === "/api/features/7/repos") {
      return jsonResponse({ repos: [] });
    }
    if (path === "/api/features/7/repos/repo_existing" && init?.method === "POST") {
      return jsonResponse(existingRepo);
    }
    if (path === "/api/features/7/repos/repo_1" && init?.method === "POST") {
      return jsonResponse({
        id: "repo_1",
        name: "codeask",
        source: "local_dir",
        url: null,
        local_path: "/repo/codeask",
        bare_path: "/tmp/repos/repo_1/bare",
        status: "registered",
        error_message: null,
        last_synced_at: null,
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00"
      });
    }
    if (path === "/api/features/7/repos/repo_existing" && init?.method === "DELETE") {
      return new Response(null, { status: 204 });
    }
    if (path === "/api/skills") {
      if (init?.method === "POST") {
        return jsonResponse({
          id: "sk_1",
          name: "支付排障",
          scope: "feature",
          feature_id: 7,
          prompt_template: "按支付链路排查"
        }, 201);
      }
      return jsonResponse([]);
    }
    throw new Error(`unexpected request ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("FeatureWorkbench management actions", () => {
  it("creates features from an inline list form", async () => {
    const fetchMock = installFeatureFetchMock();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "添加特性" }));
    fireEvent.change(screen.getByLabelText("特性名称"), { target: { value: "风控策略" } });
    fireEvent.click(screen.getByRole("button", { name: "创建特性" }));

    expect(await screen.findAllByText("risk-policy")).not.toHaveLength(0);
    const [, init] = fetchMock.mock.calls.find(([path, options]) =>
      path === "/api/features" && (options as RequestInit | undefined)?.method === "POST"
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      name: "风控策略"
    });
    expect(JSON.parse(String(init.body))).not.toHaveProperty("slug");
  });

  it("uploads wiki, shows generated reports, links a repo, and creates a feature skill in feature tabs", async () => {
    const fetchMock = installFeatureFetchMock({ repos: [existingRepo] });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));
    fireEvent.change(screen.getByLabelText("选择 Wiki 文件或目录"), {
      target: { files: [new File(["# 支付"], "payment.md", { type: "text/markdown" })] }
    });
    expect(await screen.findByText("已上传 1 个 Wiki 文件")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    expect(await screen.findByText("启动失败复盘")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /启动失败复盘/ }));
    expect(screen.getByText("配置缺失导致启动失败")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "关联仓库" }));
    fireEvent.click(await screen.findByRole("checkbox"));

    fireEvent.click(screen.getByRole("tab", { name: "特性 Skill" }));
    fireEvent.change(screen.getByLabelText("Skill 名称"), { target: { value: "支付排障" } });
    fireEvent.change(screen.getByLabelText("Prompt 模板"), { target: { value: "按支付链路排查" } });
    fireEvent.click(screen.getByRole("button", { name: "创建 Skill" }));
    expect(await screen.findByText("支付排障")).toBeInTheDocument();

    const documentUpload = fetchMock.mock.calls.find(([path, options]) =>
      path === "/api/documents" && (options as RequestInit | undefined)?.method === "POST"
    ) as unknown as [string, RequestInit];
    expect(documentUpload[1].body).toBeInstanceOf(FormData);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/features/7/repos/repo_existing",
      expect.objectContaining({ method: "POST" })
    );

    expect(within(screen.getByRole("region", { name: "特性列表" })).queryByText("Wiki")).not.toBeInTheDocument();
  });

  it("links existing global repos inside the selected feature page", async () => {
    const fetchMock = installFeatureFetchMock({ repos: [existingRepo] });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "关联仓库" }));

    expect(await screen.findAllByText(/platform-api/)).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("checkbox"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7/repos/repo_existing",
        expect.objectContaining({ method: "POST" })
      );
    });
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("deletes a feature from the feature list after confirmation", async () => {
    const fetchMock = installFeatureFetchMock();
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "删除特性 支付结算" }));
    expect(screen.getByRole("dialog", { name: "删除特性" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7",
        expect.objectContaining({ method: "DELETE" })
      );
    });
    await waitFor(() => {
      expect(within(screen.getByRole("region", { name: "特性列表" })).queryByText("支付结算")).not.toBeInTheDocument();
    });
  });
});
