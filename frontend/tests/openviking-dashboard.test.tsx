import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    vi.clearAllMocks();
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
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) => {
      const filtered = syncJobs.filter((job) => !params.status || job.status === params.status);
      const page = params.page ?? 1;
      const limit = params.limit ?? 5;
      const start = (page - 1) * limit;
      const items = filtered.slice(start, start + limit);
      return Promise.resolve({
        total: filtered.length,
        page,
        limit,
        items,
      });
    });
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 1, running: 0, failed: 1, indexed: 3, cancelled: 0 },
    });
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
      event_types: ["openviking_restart_detected", "repo_synced", "sync_job_failed"],
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
      limit: 5,
      next_before_id: null,
      page: 1,
      total: 2,
      total_pages: 1,
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
    expect(within(statusOnlyJob as HTMLElement).queryByText("状态 pending")).not.toBeInTheDocument();
    expect(within(statusOnlyJob as HTMLElement).queryByText("ETA —")).not.toBeInTheDocument();
    expect(within(statusOnlyJob as HTMLElement).getByText("等待中")).toBeInTheDocument();
    expect((statusOnlyJob as HTMLElement).getAttribute("data-status")).toBe("pending");
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
    await screen.findByText("仓库 Feature scoped claude-code 1778952333054 已同步");
    expect(screen.getAllByText("仓库已同步")).toHaveLength(2);
    expect(await screen.findByText("仓库 Feature scoped claude-code 1778952333054 已同步")).toBeInTheDocument();
    expect((await screen.findAllByText("成功")).length).toBeGreaterThan(0);
    expect(screen.queryByText("repo · f7606c2988444040")).not.toBeInTheDocument();
    expect(screen.queryByText(/×2/)).not.toBeInTheDocument();
    expect(screen.getByText("仓库 Feature scoped anything-llm 1778952333055 已同步")).toBeInTheDocument();
    expect(screen.getByLabelText("事件范围")).toHaveValue("important");
    expect(screen.getByRole("option", { name: "sync_job_failed" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "openviking_restart_detected" })).toBeInTheDocument();
    await waitFor(() =>
      expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenCalledWith(
        expect.objectContaining({ view: "important" }),
      ),
    );
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

    fireEvent.change(screen.getByLabelText("事件范围"), {
      target: { value: "all" },
    });
    await waitFor(() =>
      expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenCalledWith(
        expect.objectContaining({ view: "all" }),
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
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
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
      limit: 5,
      next_before_id: null,
      page: 1,
      total: 1,
      total_pages: 1,
    } as never);

    renderDashboard();

    expect(await screen.findByText("仓库 f7606c2988444040 已同步")).toBeInTheDocument();
  });

  it("renders actionable human readable warning and error events", async () => {
    vi.mocked(api.listOpenVikingEvents).mockResolvedValueOnce({
      items: [
        {
          id: 30,
          event_type: "scheduled_refresh_summary",
          source_type: "system",
          source_id: null,
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            scanned: 0,
            enqueued: 0,
            skipped: 0,
            error: "OpenViking health check timed out",
          },
          outcome: "error",
          created_at: "2026-05-26T10:00:00Z",
        },
        {
          id: 31,
          event_type: "sync_job_failed",
          source_type: "wiki_doc",
          source_id: "42",
          sync_job_id: "ovjob_failed_1",
          triggered_by: "system",
          payload: {
            error: "embedding backend busy",
            attempts: 2,
            operation: "upsert",
            name: "AnythingLLM 召回说明",
          },
          outcome: "warning",
          created_at: "2026-05-26T09:59:00Z",
        },
        {
          id: 32,
          event_type: "sync_job_failed",
          source_type: "wiki_doc",
          source_id: "43",
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            error: "document content missing",
            attempts: 5,
            operation: "upsert",
            name: "缺失文档",
          },
          outcome: "error",
          created_at: "2026-05-26T09:58:00Z",
        },
        {
          id: 33,
          event_type: "openviking_breaker_tripped",
          source_type: "openviking",
          source_id: null,
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            status_code: 503,
            detail: "circuit breaker open",
          },
          outcome: "warning",
          created_at: "2026-05-26T09:57:00Z",
        },
        {
          id: 34,
          event_type: "openviking_health_failed",
          source_type: "openviking",
          source_id: null,
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            pid: 4034175,
            port: 1933,
            error: "All connection attempts failed",
          },
          outcome: "warning",
          created_at: "2026-05-26T09:56:00Z",
        },
        {
          id: 35,
          event_type: "unknown_event",
          source_type: "system",
          source_id: null,
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            scanned: 0,
            enqueued: 0,
            skipped: 0,
            error: "unknown failure should not be sliced away",
          },
          outcome: "error",
          created_at: "2026-05-26T09:55:00Z",
        },
      ],
      limit: 10,
      next_before_id: null,
      page: 1,
      total: 6,
      total_pages: 1,
    });

    renderDashboard();

    expect(await screen.findByText("定时同步汇总")).toBeInTheDocument();
    expect(screen.getByText(/OpenViking health check timed out/)).toBeInTheDocument();
    expect(screen.getByText("建议：立即重新触发全量同步，确认 OpenViking 和 Ollama 健康后观察队列。")).toBeInTheDocument();
    expect(screen.getAllByText("同步任务失败")).toHaveLength(2);
    expect(screen.getByText(/embedding backend busy；AnythingLLM 召回说明索引失败/)).toBeInTheDocument();
    expect(
      screen.getAllByText("建议：重新入队该同步任务；如果连续失败，请检查资源正文和 OpenViking 日志。"),
    ).toHaveLength(2);
    expect(screen.getByText(/document content missing；缺失文档索引失败/)).toBeInTheDocument();
    expect(screen.getAllByText("重试该任务")).toHaveLength(1);

    expect(screen.getByText("OpenViking 熔断触发")).toBeInTheDocument();
    expect(screen.getByText(/OpenViking 返回 503：circuit breaker open/)).toBeInTheDocument();
    expect(
      screen.getByText("建议：OpenViking 熔断已打开；确认进程健康后稍后重试。"),
    ).toBeInTheDocument();
    expect(screen.getByText("OpenViking 健康检查失败")).toBeInTheDocument();
    expect(screen.getByText(/All connection attempts failed；pid 4034175 · 端口 1933/)).toBeInTheDocument();
    expect(
      screen.getByText("建议：OpenViking 进程未通过健康检查；请查看 OpenViking 服务日志和网络/依赖下载状态。"),
    ).toBeInTheDocument();

    expect(screen.getAllByText("unknown_event").length).toBeGreaterThan(0);
    expect(screen.getByText(/unknown failure should not be sliced away/)).toBeInTheDocument();
    expect(screen.getAllByText("错误").length).toBeGreaterThan(0);
    expect(screen.getAllByText("警告").length).toBeGreaterThan(0);

    expect(screen.queryByText("事件类型")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "详情" })[0] as HTMLElement);
    expect(screen.getByText("事件类型")).toBeInTheDocument();
    expect(screen.getAllByText("scheduled_refresh_summary").length).toBeGreaterThan(0);
    expect(screen.getByText(/"error": "OpenViking health check timed out"/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试该任务" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "确认重试同步任务" })).getByRole("button", {
      name: "确认重试",
    }));
    await waitFor(() => {
      const calls = vi.mocked(api.retrySyncJob).mock.calls;
      expect(calls.at(-1)?.[0]).toBe("ovjob_failed_1");
    });
  });

  it("runs scheduled refresh remediation from an event row", async () => {
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
      items: [
        {
          id: 40,
          event_type: "scheduled_refresh_summary",
          source_type: "system",
          source_id: null,
          sync_job_id: null,
          triggered_by: "system",
          payload: {
            scanned: 0,
            enqueued: 0,
            skipped: 0,
            error: "OpenViking health check timed out",
          },
          outcome: "error",
          created_at: "2026-05-26T10:00:00Z",
        },
      ],
      limit: 5,
      next_before_id: null,
      page: 1,
      total: 1,
      total_pages: 1,
    } as never);

    renderDashboard();

    expect(await screen.findByText("定时同步汇总")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "立即重新同步" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "确认立即重新同步" })).getByRole("button", {
      name: "确认同步",
    }));
    await waitFor(() => expect(vi.mocked(api.resyncOpenViking)).toHaveBeenCalledTimes(1));
  });

  it("shows remediation success only after the retry request succeeds", async () => {
    let resolveRetry: (value: unknown) => void = () => undefined;
    vi.mocked(api.retrySyncJob).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRetry = resolve;
        }) as never,
    );
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
      items: [
        {
          id: 31,
          event_type: "sync_job_failed",
          source_type: "wiki_doc",
          source_id: "42",
          sync_job_id: "ovjob_failed_1",
          triggered_by: "system",
          payload: {
            error: "embedding backend busy",
            attempts: 1,
            operation: "upsert",
            name: "AnythingLLM 召回说明",
          },
          outcome: "warning",
          created_at: "2026-05-26T09:59:00Z",
        },
      ],
      limit: 5,
      next_before_id: null,
      page: 1,
      total: 1,
      total_pages: 1,
    } as never);

    renderDashboard();

    expect(await screen.findByText("同步任务失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试该任务" }));
    fireEvent.click(within(await screen.findByRole("dialog", { name: "确认重试同步任务" })).getByRole("button", {
      name: "确认重试",
    }));
    await waitFor(() => expect(vi.mocked(api.retrySyncJob)).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("重试任务已提交")).not.toBeInTheDocument();

    await act(async () => {
      resolveRetry({});
    });

    expect(await screen.findByText("重试任务已提交")).toBeInTheDocument();
    expect(screen.getAllByText("重试任务已提交")).toHaveLength(1);
  });

  it("paginates event stream one page at a time without aggregating loaded pages", async () => {
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
          {
            id: 21,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_b",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo B" },
            outcome: "success",
            created_at: "2026-05-26T09:59:30Z",
          },
          {
            id: 22,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_d",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo D" },
            outcome: "success",
            created_at: "2026-05-26T09:59:20Z",
          },
          {
            id: 23,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_e",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo E" },
            outcome: "success",
            created_at: "2026-05-26T09:59:10Z",
          },
          {
            id: 24,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_f",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo F" },
            outcome: "success",
            created_at: "2026-05-26T09:59:05Z",
          },
        ],
        next_before_id: 20,
        total: 12,
        page: 1,
        limit: 5,
        total_pages: 3,
      } as never)
      .mockResolvedValueOnce({
        items: [
          {
            id: 19,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_c",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo C" },
            outcome: "success",
            created_at: "2026-05-26T09:59:00Z",
          },
        ],
        next_before_id: null,
        total: 12,
        page: 3,
        limit: 5,
        total_pages: 3,
      } as never)
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
          {
            id: 21,
            event_type: "repo_synced",
            source_type: "repo",
            source_id: "repo_b",
            sync_job_id: null,
            triggered_by: "admin",
            payload: { name: "Repo B" },
            outcome: "success",
            created_at: "2026-05-26T09:59:30Z",
          },
        ],
        next_before_id: 20,
        total: 12,
        page: 1,
        limit: 10,
        total_pages: 2,
      } as never);

    renderDashboard();

    expect(await screen.findByText("仓库 Repo A 已同步")).toBeInTheDocument();
    expect(screen.getByText("仓库 Repo B 已同步")).toBeInTheDocument();
    expect(screen.queryByText(/×2/)).not.toBeInTheDocument();
    expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 5, page: 1 }),
    );
    expect(screen.getByText("共 12 条 · 第 1 / 3 页")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("事件页码"), { target: { value: "3" } });
    fireEvent.click(await screen.findByRole("button", { name: "跳转事件页" }));
    expect(await screen.findByText("仓库 Repo C 已同步")).toBeInTheDocument();
    expect(screen.queryByText("仓库 Repo A 已同步")).not.toBeInTheDocument();
    expect(screen.queryByText("仓库 Repo B 已同步")).not.toBeInTheDocument();
    expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 5, page: 3 }),
    );
    expect(screen.getByText("共 12 条 · 第 3 / 3 页")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("事件每页条数"), { target: { value: "10" } });
    expect(await screen.findByText("仓库 Repo A 已同步")).toBeInTheDocument();
    expect(await screen.findByText("仓库 Repo B 已同步")).toBeInTheDocument();
    expect(screen.queryByText("仓库 Repo C 已同步")).not.toBeInTheDocument();
    expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenLastCalledWith(
      expect.objectContaining({ limit: 10, page: 1 }),
    );
    expect(screen.getByText("共 12 条 · 第 1 / 2 页")).toBeInTheDocument();
  });

  it("shows retry button for cancelled jobs, distinguishes failed/cancelled in status pills, and displays retry metadata", async () => {
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 0, running: 0, failed: 2, indexed: 3, cancelled: 1 },
    });
    const cancelledJob = {
      id: "ovjob_c1",
      source_type: "wiki_doc",
      source_id: "99",
      display_name: "已停止的文档",
      feature_slug: "anything-llm",
      viking_uri: "viking://resources/codeask/features/anything-llm/wiki/cancelled.md",
      status: "cancelled",
      attempts: 5,
      next_retry_at: null,
      last_synced_at: null,
      last_indexed_at: null,
      error: "Connection refused to OpenViking",
      progress: null,
      created_at: "2026-05-26T10:00:00Z",
      updated_at: "2026-05-26T10:05:00Z",
    };
    const failedJobWithRetry = {
      id: "ovjob_f1",
      source_type: "report",
      source_id: "88",
      display_name: "某故障报告",
      feature_slug: "opencode",
      viking_uri: "viking://resources/codeask/features/opencode/problem-reports/verified/report.md",
      status: "failed",
      attempts: 3,
      next_retry_at: "2026-05-26T14:30:00Z",
      last_synced_at: null,
      last_indexed_at: null,
      error: "embedding dimension mismatch",
      progress: null,
      created_at: "2026-05-26T10:00:00Z",
      updated_at: "2026-05-26T10:03:00Z",
    };
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) => {
      const allJobs = [cancelledJob, failedJobWithRetry];
      const filtered = allJobs.filter((j) => !params.status || j.status === params.status);
      const page = params.page ?? 1;
      const limit = params.limit ?? 5;
      const start = (page - 1) * limit;
      const items = filtered.slice(start, start + limit);
      return Promise.resolve({
        total: filtered.length,
        page,
        limit,
        items,
      });
    });
    vi.mocked(api.retrySyncJob).mockResolvedValue({} as never);

    renderDashboard();
    await screen.findByRole("heading", { name: "同步任务" });

    // A1: StatusPill split — separate "失败" and "已停止重试" pills
    const jobSummary = screen.getByLabelText("OpenViking 同步任务");
    const pills = jobSummary.querySelectorAll(".openviking-status-pill");
    const failedPill = Array.from(pills).find((p) => p.querySelector("span")?.textContent === "失败");
    expect(failedPill).toBeTruthy();
    await waitFor(() => expect(failedPill!.querySelector("strong")?.textContent).toBe("2"));
    const cancelledPill = Array.from(pills).find((p) => p.querySelector("span")?.textContent === "已停止重试");
    expect(cancelledPill).toBeTruthy();
    await waitFor(() => expect(cancelledPill!.querySelector("strong")?.textContent).toBe("1"));

    // A1: cancelled job shows retry button (was the bug — cancelled had no button)
    const cancelledRow = screen.getByText("已停止的文档").closest(".settings-openviking-job-row");
    expect(cancelledRow).toBeInTheDocument();
    expect(within(cancelledRow as HTMLElement).getByRole("button", { name: "重试 ovjob_c1" })).toBeInTheDocument();

    // A1: statusOutcome — cancelled gets error badge (not neutral info)
    const cancelledBadge = within(cancelledRow as HTMLElement).getByText("已停止重试");
    expect(cancelledBadge.closest(".settings-openviking-badge")?.getAttribute("data-outcome")).toBe("error");

    // A1: data-status attribute
    expect((cancelledRow as HTMLElement).getAttribute("data-status")).toBe("cancelled");

    // A2: failed job meta line — attempts + next_retry_at
    const failedRow = screen.getByText("某故障报告").closest(".settings-openviking-job-row");
    expect(failedRow).toBeInTheDocument();
    expect(within(failedRow as HTMLElement).getByText(/已重试 3 次/)).toBeInTheDocument();
    expect(within(failedRow as HTMLElement).getByText(/下次约/)).toBeInTheDocument();
    expect(within(failedRow as HTMLElement).getByText(/自动重试/)).toBeInTheDocument();

    // A2: cancelled job meta line — "已停止自动重试"
    expect(within(cancelledRow as HTMLElement).getByText("已停止自动重试")).toBeInTheDocument();

    // A3: SYNC_STATUS_LABELS — Badge uses Chinese labels
    expect(within(failedRow as HTMLElement).getByText("失败")).toBeInTheDocument();
    const failedBadge = within(failedRow as HTMLElement).getByText("失败");
    expect(failedBadge.closest(".settings-openviking-badge")?.getAttribute("data-outcome")).toBe("error");

    // A3: cancelled error hint (human-readable reason + action)
    expect(
      within(cancelledRow as HTMLElement).getByText(/已连续失败 5 次自动停止/),
    ).toBeInTheDocument();
    expect(
      within(cancelledRow as HTMLElement).getByText(/请检查 OpenViking 服务是否在线/),
    ).toBeInTheDocument();

    // A3: common error pattern mapping — embedding error gets translated
    expect(
      within(failedRow as HTMLElement).getByText(/Embedding 模型异常/),
    ).toBeInTheDocument();

    // A4: no-noise — no "ETA —" or raw "状态" line in either row
    expect(within(cancelledRow as HTMLElement).queryByText("ETA —")).not.toBeInTheDocument();
    expect(within(cancelledRow as HTMLElement).queryByText(/^状态 /)).not.toBeInTheDocument();
    expect(within(failedRow as HTMLElement).queryByText("ETA —")).not.toBeInTheDocument();
    expect(within(failedRow as HTMLElement).queryByText(/^状态 /)).not.toBeInTheDocument();
  });
});

  it("paginates sync jobs across pages and disables prev/next at boundaries", async () => {
    const manyJobs = Array.from({ length: 7 }, (_, i) => ({
      id: `ovjob_p${i + 1}`,
      source_type: "wiki_doc" as const,
      source_id: String(i + 1),
      display_name: `分页文档 ${i + 1}`,
      feature_slug: "anything-llm",
      viking_uri: `viking://resources/codeask/features/anything-llm/wiki/p${i + 1}.md`,
      status: "indexed" as const,
      attempts: 0,
      next_retry_at: null,
      last_synced_at: null,
      last_indexed_at: null,
      error: null,
      progress: null,
      created_at: "2026-05-26T10:00:00Z",
      updated_at: "2026-05-26T10:01:00Z",
    }));
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 0, running: 0, failed: 0, indexed: 7, cancelled: 0 },
    });
    let lastCallParams: Record<string, unknown> = {};
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) => {
      lastCallParams = params as Record<string, unknown>;
      const page = (params as { page?: number }).page ?? 1;
      const limit = (params as { limit?: number }).limit ?? 5;
      const start = (page - 1) * limit;
      return Promise.resolve({ total: 7, page, limit, items: manyJobs.slice(start, start + limit) });
    });

    renderDashboard();
    const syncCard = await screen.findByLabelText("OpenViking 同步任务");

    expect(await within(syncCard).findByText("分页文档 1")).toBeInTheDocument();
    expect(within(syncCard).getByText("分页文档 5")).toBeInTheDocument();
    expect(within(syncCard).queryByText("分页文档 6")).not.toBeInTheDocument();
    expect(within(syncCard).getByText("共 7 条 · 第 1 / 2 页")).toBeInTheDocument();
    expect(within(syncCard).getByRole("button", { name: "上一页同步任务" })).toBeDisabled();
    expect(within(syncCard).getByRole("button", { name: "下一页同步任务" })).toBeEnabled();

    fireEvent.click(within(syncCard).getByRole("button", { name: "下一页同步任务" }));
    await waitFor(() => expect(lastCallParams.page).toBe(2));
    expect(await within(syncCard).findByText("分页文档 6")).toBeInTheDocument();
    expect(within(syncCard).getByText("分页文档 7")).toBeInTheDocument();
    expect(within(syncCard).queryByText("分页文档 1")).not.toBeInTheDocument();
    expect(within(syncCard).getByText("共 7 条 · 第 2 / 2 页")).toBeInTheDocument();
    expect(within(syncCard).getByRole("button", { name: "下一页同步任务" })).toBeDisabled();

    fireEvent.click(within(syncCard).getByRole("button", { name: "上一页同步任务" }));
    await waitFor(() => expect(lastCallParams.page).toBe(1));
    expect(await within(syncCard).findByText("分页文档 1")).toBeInTheDocument();
    expect(within(syncCard).getByText("共 7 条 · 第 1 / 2 页")).toBeInTheDocument();
  });

  it("filters by status dropdown and resets page to 1", async () => {
    // Set up 7 items so we can paginate
    const manyJobs = Array.from({ length: 7 }, (_, i) => ({
      id: `ovjob_f${i + 1}`,
      source_type: "wiki_doc" as const,
      source_id: String(i + 1),
      display_name: `筛选文档 ${i + 1}`,
      feature_slug: "test",
      viking_uri: `viking://test/p${i + 1}.md`,
      status: "indexed" as const,
      attempts: 0,
      next_retry_at: null,
      last_synced_at: null,
      last_indexed_at: null,
      error: null,
      progress: null,
      created_at: "2026-05-26T10:00:00Z",
      updated_at: "2026-05-26T10:01:00Z",
    }));
    let lastCallParams: Record<string, unknown> = {};
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) => {
      lastCallParams = params as Record<string, unknown>;
      const page = (params as { page?: number }).page ?? 1;
      const limit = (params as { limit?: number }).limit ?? 5;
      const start = (page - 1) * limit;
      return Promise.resolve({ total: 7, page, limit, items: manyJobs.slice(start, start + limit) });
    });
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 0, running: 0, failed: 0, indexed: 7, cancelled: 0 },
    });

    renderDashboard();
    await screen.findByRole("heading", { name: "同步任务" });

    // Go to page 2 first
    await screen.findByText("筛选文档 1");
    fireEvent.click(screen.getByRole("button", { name: "下一页同步任务" }));
    await waitFor(() => expect(lastCallParams.page).toBe(2), { timeout: 3000 });

    // Now change filter — must reset to page 1
    const statusSelect = screen.getByLabelText("同步任务状态筛选");
    fireEvent.change(statusSelect, { target: { value: "failed" } });
    await waitFor(() => {
      expect(lastCallParams.status).toBe("failed");
      expect(lastCallParams.page).toBe(1);
    });
  });

  it("clicks StatusPill to filter and toggles off on second click", async () => {
    renderDashboard();
    await screen.findByRole("heading", { name: "同步任务" });

    const syncCard2 = screen.getByLabelText("OpenViking 同步任务");
    const pills = syncCard2.querySelectorAll(".openviking-status-pill[role='button']");
    const failedPill = Array.from(pills).find((p) => p.querySelector("span")?.textContent === "失败");
    expect(failedPill).toBeTruthy();
    fireEvent.click(failedPill as HTMLElement);

    await waitFor(() =>
      expect(vi.mocked(api.listOpenVikingSyncJobs)).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "failed" }),
      ),
    );

        fireEvent.click(failedPill as HTMLElement); await waitFor(() => {
      const lastCall = vi.mocked(api.listOpenVikingSyncJobs).mock.lastCall?.[0] ?? {};
      expect(lastCall.status).toBeUndefined();
    });
  });

  it("formats next_retry_at with time and date information", async () => {
    // Use a date far in the past to guarantee cross-day rendering (MM-DD HH:MM)
    const pastDate = new Date("2020-01-15T14:30:00Z");
    const job = {
      id: "ovjob_sd",
      source_type: "wiki_doc" as const,
      source_id: "sd",
      display_name: "重试文档",
      feature_slug: "test",
      viking_uri: "viking://test",
      status: "failed" as const,
      attempts: 1,
      next_retry_at: pastDate.toISOString(),
      last_synced_at: null,
      last_indexed_at: null,
      error: null,
      progress: null,
      created_at: "2026-05-26T10:00:00Z",
      updated_at: "2026-05-26T10:01:00Z",
    };
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation((params = {}) => {
      const page = (params as { page?: number }).page ?? 1;
      const limit = (params as { limit?: number }).limit ?? 5;
      return Promise.resolve({ total: 1, page, limit, items: [job].slice(0, limit) });
    });
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 0, running: 0, failed: 1, indexed: 0, cancelled: 0 },
    });

    renderDashboard();
    await screen.findByRole("heading", { name: "同步任务" });
    await screen.findByText("重试文档");
    // Cross-day (Jan 2020 is always before now): should render "01-15 HH:MM"
    const metaText = screen.getByText(/已重试 1 次 .*下次约 .* 自动重试/).textContent ?? "";
    expect(metaText).toMatch(/01-15 \d{2}:\d{2}/);
  });

  it("maps error patterns to human hints and falls back to raw error for unknowns", async () => {
    function renderWithError(error: string | null) {
      const job = {
        id: "ovjob_err",
        source_type: "wiki_doc" as const,
        source_id: "err",
        display_name: "错误测试文档",
        feature_slug: "test",
        viking_uri: "viking://test",
        status: "failed" as const,
        attempts: 1,
        next_retry_at: null,
        last_synced_at: null,
        last_indexed_at: null,
        error,
        progress: null,
        created_at: "2026-05-26T10:00:00Z",
        updated_at: "2026-05-26T10:01:00Z",
      };
      vi.mocked(api.listOpenVikingSyncJobs).mockImplementation(() =>
        Promise.resolve({ total: 1, page: 1, limit: 5, items: [job] }),
      );
      vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
        counts: { pending: 0, running: 0, failed: 1, indexed: 0, cancelled: 0 },
      });
      return renderDashboard();
    }

    const { unmount: u1 } = renderWithError("dial tcp: connection refused");
    await screen.findByText(/无法连接 OpenViking 服务/);
    u1();

    const { unmount: u2 } = renderWithError("request timed out after 30s");
    await screen.findByText(/同步超时/);
    u2();

    const { unmount: u3 } = renderWithError("unauthorized: 401 invalid token");
    await screen.findByText(/凭据或权限错误/);
    u3();

    renderWithError("some obscure internal error XYZ123");
    await screen.findByText("some obscure internal error XYZ123");
  });

  it("shows empty state with correct page text when counts are all zero", async () => {
    vi.mocked(api.getOpenVikingSyncJobsSummary).mockResolvedValue({
      counts: { pending: 0, running: 0, failed: 0, indexed: 0, cancelled: 0 },
    });
    vi.mocked(api.listOpenVikingSyncJobs).mockImplementation(() =>
      Promise.resolve({ total: 0, page: 1, limit: 5, items: [] }),
    );

    renderDashboard();
    const syncCard4 = await screen.findByLabelText("OpenViking 同步任务");

    expect(within(syncCard4).getByText("暂无同步任务")).toBeInTheDocument();
    expect(within(syncCard4).getByText("共 0 条 · 第 1 / 1 页")).toBeInTheDocument();
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
