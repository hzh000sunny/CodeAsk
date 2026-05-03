import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
  updated_at: "2026-04-30T10:00:00",
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
  updated_at: "2026-04-30T10:00:00",
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const defaultReports = [
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
    updated_at: "2026-04-30T10:00:00",
  },
];

function installFeatureFetchMock(
  options: { repos?: unknown[]; reports?: unknown[] } = {},
) {
  const reportRows = new Map<number, Record<string, unknown>>(
    (options.reports ?? defaultReports).map((report) => {
      const row = report as Record<string, unknown>;
      return [Number(row.id), { ...row }];
    }),
  );
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path === "/api/auth/me") {
        return jsonResponse({
          subject_id: "client_test",
          display_name: "client_test",
          role: "member",
          authenticated: false,
        });
      }
      if (path === "/api/features" && init?.method !== "POST") {
        return jsonResponse([feature]);
      }
      if (path === "/api/features" && init?.method === "POST") {
        return jsonResponse(
          { ...feature, id: 8, name: "风控策略", slug: "risk-policy" },
          201,
        );
      }
      if (path === "/api/features/7" && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      if (path === "/api/documents?feature_id=7") {
        return jsonResponse([]);
      }
      if (path === "/api/documents" && init?.method === "POST") {
        return jsonResponse(
          {
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
            updated_at: "2026-04-30T10:00:00",
          },
          201,
        );
      }
      if (path === "/api/reports?feature_id=7") {
        return jsonResponse(Array.from(reportRows.values()));
      }
      const reportMatch = path.match(
        /^\/api\/reports\/(\d+)(?:\/(verify|reject|unverify))?$/,
      );
      if (reportMatch) {
        const reportId = Number(reportMatch[1]);
        const action = reportMatch[2];
        const report = reportRows.get(reportId);
        if (!report) {
          return jsonResponse({ detail: "report not found" }, 404);
        }
        if (init?.method === "PUT") {
          const body = JSON.parse(String(init.body));
          const updated = {
            ...report,
            ...("title" in body ? { title: body.title } : {}),
            ...("body_markdown" in body
              ? { body_markdown: body.body_markdown }
              : {}),
            ...("metadata" in body ? { metadata_json: body.metadata } : {}),
            updated_at: "2026-04-30T12:00:00",
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "DELETE") {
          reportRows.delete(reportId);
          return new Response(null, { status: 204 });
        }
        if (init?.method === "POST" && action === "verify") {
          const updated = {
            ...report,
            status: "verified",
            verified: true,
            verified_by: "client_test",
            verified_at: "2026-04-30T12:00:00",
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "POST" && action === "reject") {
          const updated = {
            ...report,
            status: "rejected",
            verified: false,
            verified_by: null,
            verified_at: null,
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
        if (init?.method === "POST" && action === "unverify") {
          const updated = {
            ...report,
            status: "draft",
            verified: false,
            verified_by: null,
            verified_at: null,
          };
          reportRows.set(reportId, updated);
          return jsonResponse(updated);
        }
      }
      if (path === "/api/repos") {
        if (init?.method === "POST") {
          return jsonResponse(
            {
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
              updated_at: "2026-04-30T10:00:00",
            },
            201,
          );
        }
        return jsonResponse({ repos: options.repos ?? [] });
      }
      if (path === "/api/features/7/repos") {
        return jsonResponse({ repos: [] });
      }
      if (
        path === "/api/features/7/repos/repo_existing" &&
        init?.method === "POST"
      ) {
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
          updated_at: "2026-04-30T10:00:00",
        });
      }
      if (
        path === "/api/features/7/repos/repo_existing" &&
        init?.method === "DELETE"
      ) {
        return new Response(null, { status: 204 });
      }
      if (path === "/api/skills") {
        if (init?.method === "POST") {
          return jsonResponse(
            {
              id: "sk_1",
              name: "支付排障",
              scope: "feature",
              feature_id: 7,
              stage: "code_investigation",
              enabled: true,
              priority: 10,
              prompt_template: "按支付链路排查",
            },
            201,
          );
        }
        return jsonResponse([]);
      }
      throw new Error(`unexpected request ${path}`);
    },
  );
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
    fireEvent.change(screen.getByLabelText("特性名称"), {
      target: { value: "风控策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建特性" }));

    expect(await screen.findAllByText("risk-policy")).not.toHaveLength(0);
    const [, init] = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/features" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      name: "风控策略",
    });
    expect(JSON.parse(String(init.body))).not.toHaveProperty("slug");
  });

  it("uploads wiki, shows generated reports, links a repo, and creates a feature analysis policy in feature tabs", async () => {
    const fetchMock = installFeatureFetchMock({ repos: [existingRepo] });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);

    fireEvent.click(screen.getByRole("tab", { name: "知识库" }));
    fireEvent.change(screen.getByLabelText("选择 Wiki 文件或目录"), {
      target: {
        files: [new File(["# 支付"], "payment.md", { type: "text/markdown" })],
      },
    });
    expect(
      await screen.findByText("已上传 1 个 Wiki 文件"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    expect(await screen.findByText("启动失败复盘")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /启动失败复盘/ }));
    expect(screen.getByText("配置缺失导致启动失败")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "关联仓库" }));
    fireEvent.click(await screen.findByRole("checkbox"));

    fireEvent.click(screen.getByRole("tab", { name: "特性分析策略" }));
    fireEvent.click(screen.getByRole("button", { name: "添加分析策略" }));
    fireEvent.change(screen.getByLabelText("策略名称"), {
      target: { value: "支付排障" },
    });
    fireEvent.change(screen.getByLabelText("适用阶段"), {
      target: { value: "code_investigation" },
    });
    fireEvent.change(screen.getByLabelText("优先级"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Prompt 内容"), {
      target: { value: "按支付链路排查" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建分析策略" }));
    expect(await screen.findByText("支付排障")).toBeInTheDocument();

    const documentUpload = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/documents" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(documentUpload[1].body).toBeInstanceOf(FormData);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/features/7/repos/repo_existing",
      expect.objectContaining({ method: "POST" }),
    );
    const policyCreate = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/skills" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(policyCreate[1].body))).toMatchObject({
      name: "支付排障",
      scope: "feature",
      feature_id: 7,
      stage: "code_investigation",
      enabled: true,
      priority: 10,
      prompt_template: "按支付链路排查",
    });

    expect(
      within(screen.getByRole("region", { name: "特性列表" })).queryByText(
        "Wiki",
      ),
    ).not.toBeInTheDocument();
  });

  it("shows report status filters and filters reports by lifecycle state", async () => {
    installFeatureFetchMock({
      reports: [
        defaultReports[0],
        {
          ...defaultReports[0],
          id: 22,
          title: "验证通过复盘",
          body_markdown: "人工验证后的报告",
          status: "verified",
          verified: true,
          verified_by: "maintainer",
          verified_at: "2026-04-30T11:00:00",
        },
      ],
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));

    const statusTabs = await screen.findByRole("tablist", {
      name: "报告状态筛选",
    });
    expect(within(statusTabs).getByRole("tab", { name: /全部/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /草稿/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /已验证/ })).toBeInTheDocument();
    expect(within(statusTabs).getByRole("tab", { name: /未通过/ })).toBeInTheDocument();

    fireEvent.click(within(statusTabs).getByRole("tab", { name: /已验证/ }));

    expect(await screen.findByText("验证通过复盘")).toBeInTheDocument();
    expect(screen.queryByText("启动失败复盘")).not.toBeInTheDocument();
  });

  it("constrains rendered markdown report details inside the preview pane", async () => {
    installFeatureFetchMock({
      reports: [
        {
          ...defaultReports[0],
          id: 23,
          title: "长格式报告",
          body_markdown:
            "| 字段 | 值 |\n| --- | --- |\n| 路径 | `/var/log/codeask/service/node-a/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.log` |\n\n`trace_id=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`",
        },
      ],
    });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    fireEvent.click(await screen.findByRole("button", { name: /长格式报告/ }));

    const previewTitle = screen.getByText("长格式报告", {
      selector: ".report-preview-title",
    });
    const preview = previewTitle.closest(".report-preview");
    expect(preview).toBeInTheDocument();
    expect(["0", "0px"]).toContain(
      getComputedStyle(preview as Element).minWidth,
    );
    expect(getComputedStyle(preview as Element).overflowY).toBe("auto");
    expect(getComputedStyle(screen.getByRole("table")).overflowX).toBe("auto");
  });

  it("edits, verifies, rejects, un-verifies, and deletes reports from the detail pane", async () => {
    const fetchMock = installFeatureFetchMock({
      reports: [
        {
          ...defaultReports[0],
          body_markdown: "初始报告内容",
        },
      ],
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "特性" }));
    expect(await screen.findAllByText("支付结算")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "问题报告" }));
    fireEvent.click(await screen.findByRole("button", { name: /启动失败复盘/ }));

    expect(screen.getByRole("button", { name: "编辑报告" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除报告" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "验证通过" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "验证不通过" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑报告" }));
    fireEvent.change(screen.getByLabelText("报告标题"), {
      target: { value: "编辑后的复盘" },
    });
    fireEvent.change(screen.getByLabelText("报告内容"), {
      target: { value: "编辑后的报告正文" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存报告" }));
    expect(await screen.findAllByText("编辑后的复盘")).not.toHaveLength(0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21",
      expect.objectContaining({ method: "PUT" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "验证通过" }));
    expect(await screen.findByText("已验证")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/verify",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "撤销验证" }));
    expect(await screen.findByText("草稿")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/unverify",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "验证不通过" }));
    expect(await screen.findByText("未通过")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/reports/21/reject",
      expect.objectContaining({ method: "POST" }),
    );

    fireEvent.click(screen.getByRole("button", { name: "删除报告" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/reports/21",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    expect(screen.queryByText("编辑后的复盘")).not.toBeInTheDocument();
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
        expect.objectContaining({ method: "POST" }),
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
    expect(
      screen.getByRole("dialog", { name: "删除特性" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/features/7",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
    await waitFor(() => {
      expect(
        within(screen.getByRole("region", { name: "特性列表" })).queryByText(
          "支付结算",
        ),
      ).not.toBeInTheDocument();
    });
  });
});
