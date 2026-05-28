import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppFeedbackProvider } from "../src/components/feedback/AppFeedback";
import { OpenVikingDashboard } from "../src/components/settings/OpenVikingDashboard";
import * as api from "../src/lib/api";

vi.mock("../src/lib/api", () => ({
  applyOpenVikingTuning: vi.fn(),
  applyOpenVikingTuningPreset: vi.fn(),
  getOllamaSnippet: vi.fn(),
  getOpenVikingEmbedding: vi.fn(),
  getOpenVikingStatus: vi.fn(),
  getOpenVikingTuning: vi.fn(),
  getTuningPreset: vi.fn(),
  getOpenVikingSyncJobsSummary: vi.fn(),
  listEmbeddingCandidates: vi.fn(),
  listOpenVikingEvents: vi.fn(),
  listOpenVikingSyncJobs: vi.fn(),
  rebuildEmbedding: vi.fn(),
  rebuildOpenVikingIndex: vi.fn(),
  resyncOpenViking: vi.fn(),
  retryFailedSyncJobs: vi.fn(),
  retrySyncJob: vi.fn(),
  switchEmbeddingModel: vi.fn(),
  verifyOllamaSettings: vi.fn(),
}));

describe("OpenVikingDashboard", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    vi.mocked(api.getOpenVikingStatus).mockResolvedValue({
      running: true,
      degraded: false,
      port: 1933,
      pid: 101,
      version: "0.3.17",
      verified_version: "0.3.17",
      last_error: null,
      config_file: "/home/hzh/.codeask/openviking/ov.conf",
      workspace_path: "/home/hzh/.codeask/openviking/workspace",
      log_file: "/home/hzh/.codeask/openviking/logs/openviking-server.log",
      queue: { pending: 1, running: 0, failed: 1, indexed: 3, cancelled: 0 },
      metrics_5min: {
        breaker_trips: 1,
        collected: true,
        latency_p95_ms: 42,
        latency_samples: 20,
        message: null,
        throughput_per_min: 1,
        window_seconds: 300,
      },
      health: { healthy: true, version: "0.3.17", error: null },
      ollama: {
        healthy: true,
        model_available: true,
        required_model: "bge-m3",
        models: ["bge-m3:latest"],
        error: null,
      },
    });
    vi.mocked(api.getOpenVikingEmbedding).mockResolvedValue({
      id: 1,
      provider: "ollama",
      base_url: "http://127.0.0.1:11434",
      model: "bge-m3",
      dimension: 1024,
      max_concurrent: 1,
      rebuild_status: "idle",
      rebuild_progress: null,
    });
    vi.mocked(api.listEmbeddingCandidates).mockResolvedValue({
      items: [
        {
          provider: "ollama",
          base_url: "http://127.0.0.1:11434",
          model: "bge-m3",
          source: "ollama",
        },
      ],
      ollama: { healthy: true, model_available: true, error: null },
    });
    const syncJobs = [
      {
        id: "ovjob_1",
        source_type: "wiki_doc",
        source_id: "12",
        display_name: "AnythingLLM 召回说明",
        feature_slug: "anything-llm",
        viking_uri: "viking://resources/codeask/features/anything-llm/wiki/index.md",
        status: "failed",
        attempts: 2,
        next_retry_at: "2026-05-26T12:00:00Z",
        last_synced_at: null,
        last_indexed_at: null,
        error: "embedding busy",
        progress: { total: 10, indexed: 4, eta_seconds: 90 },
        created_at: "2026-05-26T10:00:00Z",
        updated_at: "2026-05-26T10:01:00Z",
      },
      {
        id: "ovjob_2",
        source_type: "wiki_doc",
        source_id: "13",
        display_name: "文档生命周期",
        feature_slug: "anything-llm",
        viking_uri: "viking://resources/codeask/features/anything-llm/wiki/overview.md",
        status: "pending",
        attempts: 0,
        next_retry_at: null,
        last_synced_at: null,
        last_indexed_at: null,
        error: null,
        progress: null,
        created_at: "2026-05-26T10:00:00Z",
        updated_at: "2026-05-26T10:01:00Z",
      },
    ];
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) =>
      Promise.resolve({
        total: syncJobs.filter((job) => !params.status || job.status === params.status).length,
        next_cursor: null,
        items: syncJobs.filter((job) => !params.status || job.status === params.status),
      }),
    );
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 1, running: 0, failed: 1, indexed: 3, cancelled: 0 },
    });
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
      items: [
        {
          id: 1,
          event_type: "repo_synced",
          source_type: "repo",
          source_id: "f7606c2988444040",
          sync_job_id: null,
          triggered_by: "admin",
          payload: {
            name: "Feature scoped claude-code 1778952333054",
          },
          outcome: "success",
          created_at: "2026-05-26T10:00:00Z",
        },
        {
          id: 2,
          event_type: "repo_synced",
          source_type: "repo",
          source_id: "f7606c2988444041",
          sync_job_id: null,
          triggered_by: "admin",
          payload: {
            name: "Feature scoped anything-llm 1778952333055",
          },
          outcome: "success",
          created_at: "2026-05-26T09:59:00Z",
        },
      ],
      next_before_id: null,
    });
    vi.mocked(api.getOpenVikingTuning).mockResolvedValue({
      preset: "small_machine",
      scopes: {
        codeask: [
          {
            key: "sync_workers",
            value: "2",
            activated_at: "2026-05-26T10:00:00Z",
            activated_by: null,
            previous_value: "1",
            recommended: "2",
            notes: "default",
          },
        ],
        openviking: [
          {
            key: "embedding.max_concurrent",
            value: "1",
            activated_at: "2026-05-26T10:00:00Z",
            activated_by: null,
            previous_value: null,
            recommended: "2",
            notes: "default",
          },
        ],
        ollama_recommend: [
          {
            key: "num_parallel",
            value: "1",
            activated_at: "2026-05-26T10:00:00Z",
            activated_by: null,
            previous_value: null,
            recommended: "1",
            notes: "default",
          },
        ],
      },
    });
    vi.mocked(api.getTuningPreset).mockResolvedValue({
      preset: "small_machine",
      detected_host: { preset: "small_machine" },
      preset_values: [],
    });
    vi.mocked(api.getOllamaSnippet).mockResolvedValue({
      snippet: "Environment=\"OLLAMA_NUM_PARALLEL=1\"",
      num_parallel: "1",
      num_thread: "4",
    });
    vi.mocked(api.retrySyncJob).mockResolvedValue({} as never);
    vi.mocked(api.retryFailedSyncJobs).mockResolvedValue({ queued: 1 });
    vi.mocked(api.applyOpenVikingTuning).mockResolvedValue({
      applied: [],
      rejected: [],
      estimated_downtime_seconds: 0,
    });
    vi.mocked(api.verifyOllamaSettings).mockResolvedValue({
      error: null,
      expected_num_parallel: 1,
      observed_parallel: 1,
      verified: true,
    });
  });

  it("renders aligned management cards and exposes sync/tuning actions", async () => {
    const { container } = renderDashboard();

    expect(await screen.findByRole("heading", { name: "健康状态" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "同步任务" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "事件流" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Embedding 模型" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "调优参数" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "运行指标" })).toBeInTheDocument();
    expect(container.querySelector(".settings-openviking-grid")).toBeInTheDocument();
    expect(container.querySelectorAll(".settings-openviking-card-header")).toHaveLength(6);
    expect(container.querySelectorAll(".section-title-row")).toHaveLength(0);
    expect(container.querySelector(".openviking-status-strip")).not.toBeInTheDocument();
    expect(container.querySelector(".openviking-dashboard")).not.toHaveStyle({
      padding: "22px",
    });
    expect(screen.queryByText("Required model")).not.toBeInTheDocument();
    expect(await screen.findByText("/home/hzh/.codeask/openviking/ov.conf")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "重建向量索引" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重排同步队列" })).toBeInTheDocument();
    const progress = await screen.findByRole("progressbar", { name: "ovjob_1 同步进度" });
    expect(progress).toHaveAttribute("value", "40");
    expect(screen.getByText("ETA 90s")).toBeInTheDocument();
    expect(screen.getByText("AnythingLLM 召回说明")).toBeInTheDocument();
    expect(screen.getByText(/wiki_doc · 12/)).toBeInTheDocument();
    const statusOnlyJob = screen.getByText("文档生命周期").closest(".settings-openviking-job-row");
    expect(statusOnlyJob).toBeTruthy();
    expect(within(statusOnlyJob as HTMLElement).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(within(statusOnlyJob as HTMLElement).getByText("状态 pending")).toBeInTheDocument();
    expect(screen.queryByText(/\?/)).not.toBeInTheDocument();
    const metricsCard = screen.getByLabelText("OpenViking 运行指标");
    expect(within(metricsCard).queryByText("等待任务")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("运行任务")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("已索引")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("失败任务")).not.toBeInTheDocument();
    expect(within(metricsCard).getByText("吞吐 / min")).toBeInTheDocument();
    expect(within(metricsCard).getByText("Latency p95")).toBeInTheDocument();
    expect(within(metricsCard).getByText("Breaker trips")).toBeInTheDocument();
    expect(within(metricsCard).getByText("Samples")).toBeInTheDocument();
    expect(within(metricsCard).getByText("42")).toBeInTheDocument();
    expect(await screen.findByText("repo · Feature scoped claude-code 1778952333054")).toBeInTheDocument();
    expect(screen.queryByText("repo · f7606c2988444040")).not.toBeInTheDocument();
    const collapsedRepoGroup = screen.getByRole("button", { name: "展开 repo_synced 事件组" });
    expect(collapsedRepoGroup).toHaveTextContent("×2");
    fireEvent.click(collapsedRepoGroup);
    expect(screen.getByRole("status")).toHaveTextContent("已展开 repo_synced 事件组");
    expect(screen.getByText("repo · Feature scoped anything-llm 1778952333055")).toBeInTheDocument();
    expect(
      await screen.findByText("用于在宿主机 Ollama 服务中应用当前配置的并发参数。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("用于在宿主机 Ollama 服务中应用推荐并发参数。")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "复制 配置文件" }));
    expect(await screen.findByRole("status")).toHaveTextContent("配置文件已复制");
    fireEvent.click(screen.getByRole("button", { name: "验证 Ollama 设置" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Ollama 设置验证");
    await waitFor(() => expect(vi.mocked(api.verifyOllamaSettings)).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/验证通过/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试 ovjob_1" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "确认重试同步任务" })).getByRole("button", {
      name: "确认重试",
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("重试任务");
    await waitFor(() => expect(vi.mocked(api.retrySyncJob).mock.calls[0]?.[0]).toBe("ovjob_1"));

    fireEvent.change(screen.getByLabelText("事件类型过滤"), {
      target: { value: "repo_synced" },
    });
    await waitFor(() =>
      expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenCalledWith(
        expect.objectContaining({ eventType: "repo_synced" }),
      ),
    );

    const tuningCard = screen.getByLabelText("OpenViking 调优参数");
    expect(within(tuningCard).getByText("当前推荐预设：small_machine · 共 3 项")).toBeInTheDocument();
    expect(within(tuningCard).queryByText(/偏离/)).not.toBeInTheDocument();
    expect(within(tuningCard).queryByText(/对齐/)).not.toBeInTheDocument();
    expect(within(tuningCard).queryByRole("button", { name: /对齐推荐/ })).not.toBeInTheDocument();
    expect(within(tuningCard).queryByRole("button", { name: /回滚/ })).not.toBeInTheDocument();
    expect(within(tuningCard).queryByText("应用自定义")).not.toBeInTheDocument();
    expect(within(tuningCard).getAllByText("展开参数")).toHaveLength(3);

    const openvikingScope = within(tuningCard).getByText("OpenViking 服务").closest("details");
    expect(openvikingScope).not.toHaveAttribute("open");
    expect(within(openvikingScope as HTMLElement).getByText("展开参数")).toBeInTheDocument();
    const openvikingSummary = within(openvikingScope as HTMLElement).getByText("OpenViking 服务").closest("summary");
    expect(openvikingSummary).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(within(openvikingScope as HTMLElement).getByText("OpenViking 服务"));
    expect(openvikingSummary).toHaveAttribute("aria-expanded", "true");
    expect(within(openvikingScope as HTMLElement).getByText("收起参数")).toBeInTheDocument();

    expect(within(tuningCard).getByText("embedding.max_concurrent")).toBeInTheDocument();
    expect(within(tuningCard).getByText("Embedding 请求并发数，CPU 环境建议保守。")).toBeInTheDocument();
    expect(within(tuningCard).getAllByText("推荐 2").length).toBeGreaterThan(0);
    expect(within(tuningCard).getByText("重启 OpenViking")).toBeInTheDocument();
    expect(within(tuningCard).getAllByText("自定义值").length).toBeGreaterThan(0);
    const tuningRow = within(tuningCard)
      .getByLabelText("自定义值 openviking.embedding.max_concurrent")
      .closest(".tuning-advanced-row");
    expect(tuningRow).not.toHaveClass("tuning-divergent-row");
    fireEvent.click(within(tuningCard).getByRole("button", { name: "应用 openviking.embedding.max_concurrent" }));
    expect(await screen.findByRole("status")).toHaveTextContent("参数值没有变化");
    expect(vi.mocked(api.applyOpenVikingTuning)).not.toHaveBeenCalled();

    fireEvent.change(within(tuningCard).getByLabelText("自定义值 openviking.embedding.max_concurrent"), {
      target: { value: "3" },
    });
    fireEvent.click(within(tuningCard).getByRole("button", { name: "应用 openviking.embedding.max_concurrent" }));
    const applyDialog = await screen.findByRole("dialog", { name: "确认应用调优参数" });
    expect(applyDialog).toHaveTextContent(
      "确认将 openviking.embedding.max_concurrent 从 1 修改为 3？该操作可能影响 OpenViking 运行。",
    );
    fireEvent.click(within(applyDialog).getByRole("button", { name: "取消" }));
    expect(vi.mocked(api.applyOpenVikingTuning)).not.toHaveBeenCalled();

    fireEvent.click(within(tuningCard).getByRole("button", { name: "应用 openviking.embedding.max_concurrent" }));
    const confirmedApplyDialog = await screen.findByRole("dialog", { name: "确认应用调优参数" });
    fireEvent.click(within(confirmedApplyDialog).getByRole("button", { name: "确认应用" }));
    expect(await screen.findByRole("status")).toHaveTextContent("调优参数");

    await waitFor(() =>
      expect(vi.mocked(api.applyOpenVikingTuning).mock.calls[0]?.[0]).toEqual({
        changes: [{ scope: "openviking", key: "embedding.max_concurrent", value: "3" }],
      }),
    );
  });

  it("shows a visible inline error when a management mutation fails", async () => {
    vi.mocked(api.applyOpenVikingTuning).mockRejectedValueOnce(
      new Error("value must be between 1 and 16"),
    );

    renderDashboard();
    const tuningCard = await screen.findByLabelText("OpenViking 调优参数");
    fireEvent.change(await within(tuningCard).findByLabelText("自定义值 openviking.embedding.max_concurrent"), {
      target: { value: "10000" },
    });
    fireEvent.click(within(tuningCard).getByRole("button", { name: "应用 openviking.embedding.max_concurrent" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "确认应用调优参数" })).getByRole("button", {
      name: "确认应用",
    }));

    expect(await within(tuningCard).findByText(/value must be between 1 and 16/)).toBeInTheDocument();
    expect(await screen.findByRole("alertdialog")).toHaveTextContent("保存调优参数失败");
  });

  it("requires centered confirmation dialogs before OpenViking dashboard mutations", async () => {
    renderDashboard();

    await screen.findByRole("heading", { name: "同步任务" });
    fireEvent.click(screen.getByRole("button", { name: "重试失败" }));
    let dialog = await screen.findByRole("dialog", { name: "确认重试失败任务" });
    expect(dialog).toHaveClass("confirm-dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(vi.mocked(api.retryFailedSyncJobs)).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重新同步" }));
    dialog = await screen.findByRole("dialog", { name: "确认重新同步" });
    fireEvent.click(within(dialog).getByRole("button", { name: "确认重新同步" }));
    await waitFor(() => expect(vi.mocked(api.resyncOpenViking)).toHaveBeenCalledTimes(1));

    const tuningCard = await screen.findByLabelText("OpenViking 调优参数");
    fireEvent.click(within(tuningCard).getByRole("button", { name: "套用预设" }));
    dialog = await screen.findByRole("dialog", { name: "确认套用预设" });
    fireEvent.click(within(dialog).getByRole("button", { name: "确认套用" }));
    await waitFor(() => expect(vi.mocked(api.applyOpenVikingTuningPreset)).toHaveBeenCalledTimes(1));
  });

  it("uses source id fallback when dashboard event has no readable payload name", async () => {
    vi.mocked(api.listOpenVikingEvents).mockResolvedValueOnce({
      items: [
        {
          id: 10,
          event_type: "repo_synced",
          source_type: "repo",
          source_id: "f7606c2988444040",
          sync_job_id: null,
          triggered_by: "admin",
          payload: {},
          outcome: "success",
          created_at: "2026-05-26T10:00:00Z",
        },
      ],
      next_before_id: null,
    });

    renderDashboard();

    expect(await screen.findByText("repo · f7606c2988444040")).toBeInTheDocument();
  });

  it("loads additional event pages without resetting the visible stream", async () => {
    vi.mocked(api.listOpenVikingEvents)
      .mockResolvedValueOnce({
        items: [
          {
            id: 20,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_a",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo A" },
            outcome: "success",
            created_at: "2026-05-26T10:00:00Z",
          },
        ],
        next_before_id: 20,
      })
      .mockResolvedValueOnce({
        items: [
          {
            id: 19,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_b",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo B" },
            outcome: "success",
            created_at: "2026-05-26T09:59:00Z",
          },
        ],
        next_before_id: null,
      });

    renderDashboard();

    expect(await screen.findByText("repo · Repo A")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "加载更多事件" }));
    const groupButton = await screen.findByRole("button", { name: "展开 repo_synced 事件组" });
    fireEvent.click(groupButton);
    expect(await screen.findByText("repo · Repo B")).toBeInTheDocument();
    expect(screen.getByText("已加载全部事件，刷新自动暂停。返回顶部以恢复实时刷新")).toBeInTheDocument();
  });
});

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <AppFeedbackProvider>
      <QueryClientProvider client={client}>
        <OpenVikingDashboard />
      </QueryClientProvider>
    </AppFeedbackProvider>,
  );
}
