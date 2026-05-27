import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  listEmbeddingCandidates: vi.fn(),
  listOpenVikingEvents: vi.fn(),
  listOpenVikingSyncJobs: vi.fn(),
  rebuildEmbedding: vi.fn(),
  rebuildOpenVikingIndex: vi.fn(),
  resyncOpenViking: vi.fn(),
  retryFailedSyncJobs: vi.fn(),
  retrySyncJob: vi.fn(),
  rollbackOpenVikingTuning: vi.fn(),
  switchEmbeddingModel: vi.fn(),
}));

describe("OpenVikingDashboard", () => {
  beforeEach(() => {
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
        breaker_trips: null,
        collected: false,
        latency_p95_ms: null,
        message: "未采集",
        throughput_per_min: null,
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
    vi.mocked(api.listOpenVikingSyncJobs).mockResolvedValue({
      total: 1,
      items: [
        {
          id: "ovjob_1",
          source_type: "wiki_doc",
          source_id: "12",
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
      ],
    });
    vi.mocked(api.listOpenVikingEvents).mockResolvedValue({
      items: [
        {
          id: 1,
          event_type: "tuning_change",
          source_type: "wiki_doc",
          source_id: "12",
          sync_job_id: "ovjob_1",
          triggered_by: "admin",
          payload: {
            key: "sync_workers",
            value_after: "2",
            value_before: "1",
            scope: "codeask",
          },
          outcome: "info",
          created_at: "2026-05-26T10:00:00Z",
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
    const statusOnlyJob = screen.getByText("13").closest(".settings-openviking-job-row");
    expect(statusOnlyJob).toBeTruthy();
    expect(within(statusOnlyJob as HTMLElement).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(within(statusOnlyJob as HTMLElement).getByText("状态 pending")).toBeInTheDocument();
    expect(screen.queryByText(/\?/)).not.toBeInTheDocument();
    expect(screen.getAllByText("未采集").length).toBeGreaterThan(0);
    const metricsCard = screen.getByLabelText("OpenViking 运行指标");
    expect(within(metricsCard).queryByText("等待任务")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("运行任务")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("已索引")).not.toBeInTheDocument();
    expect(within(metricsCard).queryByText("失败任务")).not.toBeInTheDocument();
    expect(within(metricsCard).getByText("吞吐 / min")).toBeInTheDocument();
    expect(within(metricsCard).getByText("Latency p95")).toBeInTheDocument();
    expect(within(metricsCard).getByText("Breaker trips")).toBeInTheDocument();
    expect(await screen.findByText(/codeask\.sync_workers: 1 → 2/)).toBeInTheDocument();
    expect(
      await screen.findByText("用于在宿主机 Ollama 服务中应用当前配置的并发参数。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("用于在宿主机 Ollama 服务中应用推荐并发参数。")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重试 ovjob_1" }));
    await waitFor(() => expect(vi.mocked(api.retrySyncJob).mock.calls[0]?.[0]).toBe("ovjob_1"));

    fireEvent.change(screen.getByLabelText("事件类型过滤"), {
      target: { value: "tuning_change" },
    });
    await waitFor(() =>
      expect(vi.mocked(api.listOpenVikingEvents)).toHaveBeenCalledWith(
        expect.objectContaining({ eventType: "tuning_change" }),
      ),
    );

    const tuningCard = screen.getByLabelText("OpenViking 调优参数");
    fireEvent.change(within(tuningCard).getByLabelText("codeask.sync_workers"), {
      target: { value: "3" },
    });
    const syncWorkersRow = within(tuningCard)
      .getByLabelText("codeask.sync_workers")
      .closest(".settings-openviking-tuning-row");
    expect(syncWorkersRow).toBeTruthy();
    expect(within(syncWorkersRow as HTMLElement).getByText("推荐值")).toBeInTheDocument();
    expect(within(syncWorkersRow as HTMLElement).getByRole("button", { name: "应用 codeask.sync_workers" })).toHaveTextContent("应用");
    fireEvent.click(within(syncWorkersRow as HTMLElement).getByRole("button", { name: "应用 codeask.sync_workers" }));

    await waitFor(() =>
      expect(vi.mocked(api.applyOpenVikingTuning).mock.calls[0]?.[0]).toEqual({
        changes: [{ scope: "codeask", key: "sync_workers", value: "3" }],
      }),
    );

    const maxConcurrentRow = within(tuningCard)
      .getByLabelText("openviking.embedding.max_concurrent")
      .closest(".settings-openviking-tuning-row");
    expect(maxConcurrentRow).toBeTruthy();
    expect(maxConcurrentRow).toHaveAttribute("data-recommendation", "changed");
    expect(within(maxConcurrentRow as HTMLElement).getByText("偏离推荐")).toBeInTheDocument();
  });

  it("shows a visible inline error when a management mutation fails", async () => {
    vi.mocked(api.applyOpenVikingTuning).mockRejectedValueOnce(
      new Error("value must be between 1 and 16"),
    );

    renderDashboard();
    const tuningCard = await screen.findByLabelText("OpenViking 调优参数");
    fireEvent.change(await within(tuningCard).findByLabelText("codeask.sync_workers"), {
      target: { value: "10000" },
    });
    fireEvent.click(within(tuningCard).getByRole("button", { name: "应用 codeask.sync_workers" }));

    expect(await within(tuningCard).findByText(/value must be between 1 and 16/)).toBeInTheDocument();
  });
});

function renderDashboard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OpenVikingDashboard />
    </QueryClientProvider>,
  );
}
