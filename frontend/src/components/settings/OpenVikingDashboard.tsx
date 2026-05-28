import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Copy,
  Database,
  Gauge,
  ListChecks,
  SlidersHorizontal,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  applyOpenVikingTuning,
  applyOpenVikingTuningPreset,
  getOllamaSnippet,
  getOpenVikingEmbedding,
  getOpenVikingStatus,
  getOpenVikingSyncJobsSummary,
  getOpenVikingTuning,
  getTuningPreset,
  listEmbeddingCandidates,
  listOpenVikingEvents,
  listOpenVikingSyncJobs,
  rebuildEmbedding,
  rebuildOpenVikingIndex,
  resyncOpenViking,
  retryFailedSyncJobs,
  retrySyncJob,
  switchEmbeddingModel,
  verifyOllamaSettings,
} from "../../lib/api";
import type {
  OpenVikingDashboardEvent,
  OpenVikingEmbeddingCandidate,
  OpenVikingEmbeddingResponse,
  OpenVikingStatusResponse,
  OpenVikingSyncJob,
  OpenVikingTuningApplyResponse,
  OpenVikingTuningItem,
  OpenVikingTuningResponse,
} from "../../types/api";
import { useAppFeedback } from "../feedback/AppFeedback";
import { messageFromApiError } from "./settings-utils";

type TuningRow = OpenVikingTuningItem & { scope: string };
type EventGroup = {
  count: number;
  event: OpenVikingDashboardEvent;
  events: OpenVikingDashboardEvent[];
};
type DashboardConfirmRequest = {
  confirmLabel: string;
  message: string;
  onConfirm: () => void;
  title: string;
  tone?: "danger" | "warning";
};
type DashboardFeedback = {
  showError: (message: string, options?: { title?: string }) => void;
  showSuccess: (message: string) => void;
};
type DashboardConfirm = (request: DashboardConfirmRequest) => void;

const EMPTY_VALUE = "—";
const EVENT_PAGE_SIZE = 10;
const JOB_PAGE_SIZE = 10;

const SCOPE_LABELS: Record<string, string> = {
  codeask: "CodeAsk 同步",
  ollama_recommend: "Ollama 建议",
  openviking: "OpenViking 服务",
};

const TUNING_DESCRIPTIONS: Record<string, { description: string; impact: string }> = {
  "codeask.progress_sweep_interval_seconds": {
    description: "后台刷新同步进度的间隔。",
    impact: "运行时生效",
  },
  "codeask.scheduled_refresh_hours": {
    description: "补偿性全量刷新间隔。",
    impact: "定时任务生效",
  },
  "codeask.sync_workers": {
    description: "CodeAsk 同步队列的并发 worker 数。",
    impact: "运行时生效",
  },
  "ollama_recommend.num_parallel": {
    description: "建议写入 Ollama 的并发请求数。",
    impact: "需手动应用到 Ollama",
  },
  "ollama_recommend.num_thread": {
    description: "建议写入 Ollama 的推理线程数。",
    impact: "需手动应用到 Ollama",
  },
  "openviking.circuit_breaker.failure_threshold": {
    description: "连续失败达到该阈值后触发熔断。",
    impact: "重启 OpenViking",
  },
  "openviking.circuit_breaker.reset_timeout": {
    description: "熔断后等待重试的时间窗口。",
    impact: "重启 OpenViking",
  },
  "openviking.embedding.max_concurrent": {
    description: "Embedding 请求并发数，CPU 环境建议保守。",
    impact: "重启 OpenViking",
  },
  "openviking.embedding.max_input_tokens": {
    description: "单次 embedding 输入 token 上限。",
    impact: "重启 OpenViking",
  },
  "openviking.embedding.max_retries": {
    description: "Embedding 请求失败后的重试次数。",
    impact: "重启 OpenViking",
  },
};

export function OpenVikingDashboard() {
  const queryClient = useQueryClient();
  const feedback = useAppFeedback();
  const [confirmRequest, setConfirmRequest] = useState<DashboardConfirmRequest | null>(null);
  const [eventOutcome, setEventOutcome] = useState("");
  const [eventType, setEventType] = useState("");
  const refresh = () => {
    void queryClient.invalidateQueries({
      predicate: (query) => String(query.queryKey[0]).startsWith("admin-openviking"),
    });
  };

  const statusQuery = useQuery({
    queryKey: ["admin-openviking-status"],
    queryFn: getOpenVikingStatus,
    refetchInterval: 5000,
  });
  const eventsQuery = useInfiniteQuery({
    queryKey: ["admin-openviking-events", eventOutcome, eventType],
    queryFn: ({ pageParam }) =>
      listOpenVikingEvents({
        eventType: eventType || undefined,
        outcome: eventOutcome || undefined,
        beforeId: pageParam,
        limit: EVENT_PAGE_SIZE,
      }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before_id ?? undefined,
    refetchInterval: (query) => (query.state.data?.pages.length === 1 ? 5000 : false),
  });
  const embeddingQuery = useQuery({
    queryKey: ["admin-openviking-embedding"],
    queryFn: getOpenVikingEmbedding,
  });
  const candidatesQuery = useQuery({
    queryKey: ["admin-openviking-embedding-candidates"],
    queryFn: listEmbeddingCandidates,
  });
  const tuningQuery = useQuery({
    queryKey: ["admin-openviking-tuning"],
    queryFn: getOpenVikingTuning,
  });
  const presetQuery = useQuery({
    queryKey: ["admin-openviking-tuning-preset"],
    queryFn: getTuningPreset,
  });
  const snippetQuery = useQuery({
    queryKey: ["admin-openviking-ollama-snippet"],
    queryFn: getOllamaSnippet,
  });

  const events = useMemo(
    () => eventsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [eventsQuery.data],
  );
  const eventPagesLoaded = eventsQuery.data?.pages.length ?? 0;

  function handleOutcomeChange(value: string) {
    setEventOutcome(value);
  }

  function handleEventTypeChange(value: string) {
    setEventType(value);
  }

  return (
    <div className="openviking-dashboard">
      <div className="settings-openviking-grid">
        <OpenVikingHealthCard
          status={statusQuery.data}
          feedback={feedback}
          loading={statusQuery.isLoading}
          error={statusQuery.isError ? "读取 OpenViking 状态失败" : null}
        />
        <OpenVikingEmbeddingCard
          embedding={embeddingQuery.data}
          candidates={candidatesQuery.data?.items ?? []}
          feedback={feedback}
          loading={embeddingQuery.isLoading}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
        <OpenVikingSyncJobsCard
          feedback={feedback}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
        <OpenVikingEventStream
          events={events}
          feedback={feedback}
          outcome={eventOutcome}
          eventType={eventType}
          onOutcomeChange={handleOutcomeChange}
          onEventTypeChange={handleEventTypeChange}
          hasNext={Boolean(eventsQuery.hasNextPage)}
          isLoadingMore={eventsQuery.isFetchingNextPage}
          realtimePaused={eventPagesLoaded > 1}
          onLoadMore={() => {
            feedback.showSuccess("正在加载更多事件");
            void eventsQuery
              .fetchNextPage()
              .then(() => feedback.showSuccess("事件已加载"))
              .catch((error: unknown) =>
                feedback.showError(`加载更多事件失败：${messageFromApiError(error)}`),
              );
          }}
          onReturnTop={() => {
            feedback.showSuccess("已返回事件流顶部");
            void queryClient.resetQueries({
              queryKey: ["admin-openviking-events", eventOutcome, eventType],
            });
          }}
        />
        <OpenVikingMetricsCard status={statusQuery.data} />
        <OpenVikingTuningCard
          feedback={feedback}
          tuning={tuningQuery.data}
          preset={presetQuery.data?.preset ?? tuningQuery.data?.preset ?? EMPTY_VALUE}
          snippet={snippetQuery.data?.snippet ?? ""}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
      </div>
      {confirmRequest ? (
        <OpenVikingConfirmDialog
          request={confirmRequest}
          onCancel={() => setConfirmRequest(null)}
          onConfirm={() => {
            const action = confirmRequest.onConfirm;
            setConfirmRequest(null);
            action();
          }}
        />
      ) : null}
    </div>
  );
}

function OpenVikingConfirmDialog({
  onCancel,
  onConfirm,
  request,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  request: DashboardConfirmRequest;
}) {
  const tone = request.tone ?? "warning";
  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="openviking-confirm-title"
        aria-modal="true"
        className="confirm-dialog"
        role="dialog"
      >
        <div className={`dialog-icon ${tone}`}>
          <AlertTriangle aria-hidden="true" size={18} />
        </div>
        <div className="dialog-content">
          <h2 id="openviking-confirm-title">{request.title}</h2>
          <p>{request.message}</p>
          <div className="dialog-actions">
            <button className="button button-secondary" type="button" onClick={onCancel}>
              取消
            </button>
            <button
              className={`button ${tone === "danger" ? "button-danger" : "button-primary"}`}
              type="button"
              onClick={onConfirm}
            >
              {request.confirmLabel}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function StatusPill({
  label,
  tone = "info",
  value,
}: {
  label: string;
  tone?: "info" | "success" | "warning" | "error";
  value: string;
}) {
  return (
    <div className="openviking-status-pill" data-outcome={tone}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function OpenVikingCardHeader({
  actions,
  description,
  icon,
  title,
}: {
  actions?: ReactNode;
  description: string;
  icon: ReactNode;
  title: string;
}) {
  return (
    <div className="settings-openviking-card-header">
      <div className="settings-openviking-card-title">
        <span className="settings-openviking-card-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </div>
      {actions ? <div className="settings-openviking-card-actions">{actions}</div> : null}
    </div>
  );
}

function OpenVikingHealthCard({
  feedback,
  status,
  loading,
  error,
}: {
  feedback: DashboardFeedback;
  status?: OpenVikingStatusResponse;
  loading: boolean;
  error: string | null;
}) {
  const running = status?.running ?? false;
  return (
    <section className="surface openviking-card openviking-card-health" aria-label="OpenViking 健康状态">
      <OpenVikingCardHeader
        description="服务进程、健康探针、Ollama 可用性与运行路径。"
        icon={<Database aria-hidden="true" size={16} />}
        title="健康状态"
      />
      {loading ? <p className="empty-note">正在读取 OpenViking 状态</p> : null}
      {error ? <StatusError text={error} /> : null}
      {status ? (
        <>
          <div className="settings-runtime-summary" data-running={running && !status.degraded}>
            <div className="settings-runtime-status">
              <span className="settings-runtime-status-icon">
                {running && !status.degraded ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
              </span>
              <div>
                <span>运行状态</span>
                <strong>{running && !status.degraded ? "running" : "degraded"}</strong>
              </div>
            </div>
            <p>
              {running
                ? "异常会进入 degraded，用户会话保持降级可用。"
                : "进程未运行时语义检索不可用，Wiki 搜索回退到 SQL。"}
            </p>
          </div>
          <div className="settings-diagnostic-grid settings-diagnostic-grid-fixed">
            <Metric label="端口" value={status.port} />
            <Metric label="PID" value={status.pid} />
            <Metric label="版本" value={status.version ?? status.verified_version} />
            <Metric label="OpenViking /health" value={status.health?.healthy ? "healthy" : "degraded"} />
            <Metric label="Ollama / 模型" value={status.ollama?.model_available ? "ready" : "missing"} />
          </div>
          <div className="settings-runtime-paths">
            <PathBlock feedback={feedback} label="配置文件" value={status.config_file} />
            <PathBlock feedback={feedback} label="工作目录" value={status.workspace_path} />
            <PathBlock feedback={feedback} label="日志文件" value={status.log_file} />
          </div>
          {status.last_error ? <StatusError text={status.last_error} /> : null}
          {status.health?.error ? <StatusError text={status.health.error} /> : null}
          {status.ollama?.error ? <StatusError text={status.ollama.error} /> : null}
        </>
      ) : null}
    </section>
  );
}

function OpenVikingEmbeddingCard({
  embedding,
  candidates,
  feedback,
  loading,
  onRefresh,
  requestConfirm,
}: {
  embedding?: OpenVikingEmbeddingResponse;
  candidates: OpenVikingEmbeddingCandidate[];
  feedback: DashboardFeedback;
  loading: boolean;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const [selectedModel, setSelectedModel] = useState("");
  const switchMutation = useMutation({
    mutationFn: switchEmbeddingModel,
    onError: (error) =>
      feedback.showError(`切换 Embedding 模型失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("Embedding 模型切换已提交");
    },
  });
  const rebuildMutation = useMutation({
    mutationFn: rebuildEmbedding,
    onError: (error) =>
      feedback.showError(`重建向量索引失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("向量索引重建已提交");
    },
  });
  const mutationError =
    mutationErrorMessage(switchMutation.error) ?? mutationErrorMessage(rebuildMutation.error);
  const selectedCandidate =
    candidates.find((candidate) => candidate.model === selectedModel) ?? candidates[0];
  const rebuildProgress = syncProgressView(embedding?.rebuild_progress);

  useEffect(() => {
    if (!selectedModel && embedding?.model) {
      setSelectedModel(embedding.model);
    }
  }, [embedding?.model, selectedModel]);

  function handleSwitchEmbedding() {
    if (!embedding || !selectedCandidate) {
      return;
    }
    requestConfirm({
      confirmLabel: "确认切换",
      message: `确认将 Embedding 模型从 ${embedding.model} 切换为 ${selectedCandidate.model}？这会清理索引并触发全量重建。`,
      onConfirm: () => {
        feedback.showSuccess("Embedding 模型切换已提交");
        switchMutation.mutate({
          provider: selectedCandidate.provider,
          base_url: selectedCandidate.base_url,
          model: selectedCandidate.model,
          dimension: embedding.dimension,
          max_concurrent: embedding.max_concurrent,
        });
      },
      title: "确认切换 Embedding 模型",
      tone: "danger",
    });
  }

  function handleRebuildEmbedding() {
    requestConfirm({
      confirmLabel: "确认重建",
      message: "确认重新构建 OpenViking 语义索引？过程中检索可能降级。",
      onConfirm: () => {
        feedback.showSuccess("向量索引重建已提交");
        rebuildMutation.mutate();
      },
      title: "确认重建向量索引",
      tone: "danger",
    });
  }

  return (
    <section className="surface openviking-card openviking-card-embedding" aria-label="OpenViking Embedding">
      <OpenVikingCardHeader
        description="语义索引使用的向量模型、候选切换与向量重建入口。"
        icon={<Database aria-hidden="true" size={16} />}
        title="Embedding 模型"
      />
      {loading ? <p className="empty-note">正在读取 Embedding 配置</p> : null}
      {embedding ? (
        <>
          <div className="settings-diagnostic-grid settings-diagnostic-grid-compact">
            <Metric label="Provider" value={embedding.provider} />
            <Metric label="Base URL" value={embedding.base_url} />
            <Metric label="当前模型" value={embedding.model} />
            <Metric label="维度" value={embedding.dimension} />
            <Metric label="最大并发" value={embedding.max_concurrent} />
            <Metric label="重建状态" value={embedding.rebuild_status} />
          </div>
          {rebuildProgress.value !== null ? (
            <div className="settings-openviking-progress settings-openviking-progress-block">
              <progress aria-label="Embedding 重建进度" max={100} value={rebuildProgress.value} />
              <small>
                {rebuildProgress.label} · ETA {rebuildProgress.eta}
              </small>
            </div>
          ) : null}
          <div className="settings-openviking-controls settings-openviking-embedding-controls">
            <label className="settings-openviking-field">
              <span>候选模型</span>
              <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                {candidates.length === 0 ? <option value={embedding.model}>{embedding.model}</option> : null}
                {candidates.map((candidate) => (
                  <option value={candidate.model} key={`${candidate.source}:${candidate.model}`}>
                    {candidate.model}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="button button-secondary"
              type="button"
              onClick={handleSwitchEmbedding}
              disabled={!selectedCandidate || selectedCandidate.model === embedding.model}
            >
              切换
            </button>
            <button className="button button-danger" type="button" onClick={handleRebuildEmbedding}>
              重建向量索引
            </button>
          </div>
          <p className="settings-openviking-muted">
            切换模型会清空索引并重新排队同步任务；重建向量索引只重新生成当前语义索引。
          </p>
          {mutationError ? <StatusError text={mutationError} /> : null}
        </>
      ) : null}
    </section>
  );
}

function OpenVikingSyncJobsCard({
  feedback,
  onRefresh,
  requestConfirm,
}: {
  feedback: DashboardFeedback;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const summaryQuery = useQuery({
    queryKey: ["admin-openviking-sync-jobs-summary"],
    queryFn: getOpenVikingSyncJobsSummary,
    refetchInterval: 5000,
  });
  const retryMutation = useMutation({
    mutationFn: retrySyncJob,
    onError: (error) => feedback.showError(`重试任务失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("重试任务已提交");
    },
  });
  const retryFailedMutation = useMutation({
    mutationFn: retryFailedSyncJobs,
    onError: (error) => feedback.showError(`重试失败任务失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("失败任务已重新入队");
    },
  });
  const resyncMutation = useMutation({
    mutationFn: resyncOpenViking,
    onError: (error) => feedback.showError(`重新同步失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("重新同步已提交");
    },
  });
  const rebuildMutation = useMutation({
    mutationFn: rebuildOpenVikingIndex,
    onError: (error) => feedback.showError(`重排同步队列失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("同步队列重排已提交");
    },
  });
  const mutationError =
    mutationErrorMessage(retryMutation.error) ??
    mutationErrorMessage(retryFailedMutation.error) ??
    mutationErrorMessage(resyncMutation.error) ??
    mutationErrorMessage(rebuildMutation.error);
  const counts = summaryQuery.data?.counts ?? {};

  function confirmRetryFailed() {
    requestConfirm({
      confirmLabel: "确认重试",
      message: "确认将当前失败的 OpenViking 同步任务重新入队？",
      onConfirm: () => {
        feedback.showSuccess("失败任务已重新入队");
        retryFailedMutation.mutate();
      },
      title: "确认重试失败任务",
    });
  }

  function confirmResync() {
    requestConfirm({
      confirmLabel: "确认重新同步",
      message: "确认重新同步已发布 Wiki 与已验证报告？这会新增同步任务。",
      onConfirm: () => {
        feedback.showSuccess("重新同步已提交");
        resyncMutation.mutate({});
      },
      title: "确认重新同步",
    });
  }

  function handleRebuild() {
    requestConfirm({
      confirmLabel: "确认重排",
      message: "确认重排同步队列？这会将已发布知识重新加入同步队列。",
      onConfirm: () => {
        feedback.showSuccess("同步队列重排已提交");
        rebuildMutation.mutate();
      },
      title: "确认重排同步队列",
      tone: "danger",
    });
  }

  return (
    <section className="surface openviking-card openviking-card-sync" aria-label="OpenViking 同步任务">
      <OpenVikingCardHeader
        actions={
          <>
            <button
              className="button button-secondary"
              type="button"
              onClick={confirmRetryFailed}
            >
              重试失败
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={confirmResync}
            >
              重新同步
            </button>
            <button className="button button-danger" type="button" onClick={handleRebuild}>
              重排同步队列
            </button>
          </>
        }
        description="队列、失败重试和重新排队操作入口。"
        icon={<ListChecks aria-hidden="true" size={16} />}
        title="同步任务"
      />
      <div className="settings-openviking-job-summary">
        <StatusPill label="pending" value={String(counts.pending ?? 0)} />
        <StatusPill label="running" value={String(counts.running ?? 0)} />
        <StatusPill
          label="failed"
          value={String((counts.failed ?? 0) + (counts.cancelled ?? 0))}
          tone={(counts.failed ?? 0) + (counts.cancelled ?? 0) ? "error" : "info"}
        />
        <StatusPill label="indexed" value={String(counts.indexed ?? 0)} tone="success" />
      </div>
      <p className="settings-openviking-muted">
        重排同步队列会重新安排已发布 Wiki 和已验证报告同步；不会切换 Embedding 模型。
      </p>
      <div className="settings-openviking-job-groups">
        {[
          ["failed", "失败任务"],
          ["cancelled", "已取消"],
          ["running", "运行中"],
          ["pending", "等待中"],
          ["indexed", "已索引"],
        ].map(([status, label]) => (
          <SyncJobStatusGroup
            count={counts[status] ?? 0}
            feedback={feedback}
            key={status}
            label={label}
            onRetry={(jobId) => {
              requestConfirm({
                confirmLabel: "确认重试",
                message: `确认重试同步任务 ${jobId}？`,
                onConfirm: () => {
                  feedback.showSuccess("重试任务已提交");
                  retryMutation.mutate(jobId);
                },
                title: "确认重试同步任务",
              });
            }}
            status={status}
          />
        ))}
      </div>
      {mutationError ? <StatusError text={mutationError} /> : null}
      {Object.values(counts).every((count) => count === 0) ? <p className="empty-note">暂无同步任务</p> : null}
    </section>
  );
}

function SyncJobStatusGroup({
  count,
  feedback,
  label,
  onRetry,
  status,
}: {
  count: number;
  feedback: DashboardFeedback;
  label: string;
  onRetry: (jobId: string) => void;
  status: string;
}) {
  const defaultOpen = status === "failed" || status === "running" || status === "pending";
  const jobsQuery = useInfiniteQuery({
    queryKey: ["admin-openviking-sync-jobs", status],
    queryFn: ({ pageParam }) =>
      listOpenVikingSyncJobs({
        cursor: pageParam,
        limit: JOB_PAGE_SIZE,
        status,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: count > 0,
    refetchInterval: status === "pending" || status === "running" || status === "failed" ? 5000 : false,
  });
  const jobs = jobsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  if (count <= 0) {
    return null;
  }
  return (
    <details className="settings-openviking-job-group" open={defaultOpen}>
      <summary>
        <span>{label}</span>
        <strong>{count}</strong>
      </summary>
      <ul className="data-list settings-config-list settings-openviking-job-list">
        {jobs.map((job) => (
          <SyncJobItem job={job} key={job.id} onRetry={() => onRetry(job.id)} />
        ))}
      </ul>
      {jobsQuery.hasNextPage ? (
        <button
          className="button button-secondary settings-openviking-load-more"
          type="button"
          onClick={() => {
            feedback.showSuccess(`正在加载${label}`);
            void jobsQuery
              .fetchNextPage()
              .then(() => feedback.showSuccess(`${label}已加载`))
              .catch((error: unknown) =>
                feedback.showError(`加载更多${label}失败：${messageFromApiError(error)}`),
              );
          }}
          disabled={jobsQuery.isFetchingNextPage}
        >
          加载更多
        </button>
      ) : null}
      {jobs.length === 0 && jobsQuery.isLoading ? <p className="empty-note">正在读取{label}</p> : null}
    </details>
  );
}

function SyncJobItem({ job, onRetry }: { job: OpenVikingSyncJob; onRetry: () => void }) {
  const progress = syncProgressView(job.progress);
  return (
    <li className="settings-openviking-job-row">
      <div className="settings-openviking-row-main">
        <strong>{job.display_name ?? job.source_type}</strong>
        <span>
          {job.source_type} · {job.source_id}
        </span>
        {job.feature_slug ? <small>{job.feature_slug}</small> : null}
      </div>
      {progress.value !== null ? (
        <div className="settings-openviking-progress">
          <progress
            aria-label={`${job.id} 同步进度`}
            max={100}
            value={progress.value}
          />
          <small>进度 {progress.label}</small>
          <small>ETA {progress.eta}</small>
        </div>
      ) : (
        <div className="settings-openviking-progress settings-openviking-status-only">
          <small>状态 {job.status}</small>
          <small>ETA {EMPTY_VALUE}</small>
        </div>
      )}
      <Badge text={job.status} outcome={statusOutcome(job.status)} />
      {job.status === "failed" ? (
        <button
          aria-label={`重试 ${job.id}`}
          className="button button-secondary"
          type="button"
          onClick={onRetry}
        >
          重试
        </button>
      ) : null}
      {job.error ? <small className="settings-openviking-error" title={job.error}>{job.error}</small> : null}
    </li>
  );
}

function OpenVikingEventStream({
  events,
  feedback,
  outcome,
  eventType,
  onOutcomeChange,
  onEventTypeChange,
  hasNext,
  isLoadingMore,
  onLoadMore,
  onReturnTop,
  realtimePaused,
}: {
  events: OpenVikingDashboardEvent[];
  feedback: DashboardFeedback;
  outcome: string;
  eventType: string;
  onOutcomeChange: (value: string) => void;
  onEventTypeChange: (value: string) => void;
  hasNext: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  onReturnTop: () => void;
  realtimePaused: boolean;
}) {
  const eventTypes = Array.from(
    new Set(
      [...events.map((event) => event.event_type), eventType].filter(
        (value): value is string => Boolean(value),
      ),
    ),
  ).sort();
  const groupedEvents = useMemo(() => collapseConsecutiveEvents(events), [events]);
  return (
    <section className="surface openviking-card openviking-card-events" aria-label="OpenViking 事件流">
      <OpenVikingCardHeader
        description="同步、调优、重启和错误事件的时间线。"
        icon={<Activity aria-hidden="true" size={16} />}
        title="事件流"
      />
      <div className="settings-openviking-filter-row">
        <label className="settings-openviking-field">
          <span>事件结果过滤</span>
          <select value={outcome} onChange={(event) => onOutcomeChange(event.target.value)}>
            <option value="">全部</option>
            <option value="info">info</option>
            <option value="success">success</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
        <label className="settings-openviking-field">
          <span>事件类型过滤</span>
          <select value={eventType} onChange={(event) => onEventTypeChange(event.target.value)}>
            <option value="">全部</option>
            {eventTypes.map((type) => (
              <option value={type} key={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ul className="data-list settings-config-list settings-openviking-event-list">
        {groupedEvents.map((group) => (
          <EventItem feedback={feedback} group={group} key={`${group.event.id}:${group.count}`} />
        ))}
      </ul>
      {events.length === 0 ? <p className="empty-note">暂无 OpenViking 事件</p> : null}
      {hasNext ? (
        <button
          className="button button-secondary settings-openviking-load-more"
          type="button"
          onClick={onLoadMore}
          disabled={isLoadingMore}
        >
          加载更多事件
        </button>
      ) : null}
      {realtimePaused && !hasNext ? (
        <div className="settings-openviking-paused-note">
          <span>已加载全部事件，刷新自动暂停。返回顶部以恢复实时刷新</span>
          <button className="button button-quiet" type="button" onClick={onReturnTop}>
            返回顶部
          </button>
        </div>
      ) : null}
    </section>
  );
}

function EventItem({
  feedback,
  group,
}: {
  feedback: DashboardFeedback;
  group: EventGroup;
}) {
  const { event } = group;
  const [expanded, setExpanded] = useState(false);
  return (
    <li className="settings-openviking-row" data-outcome={event.outcome}>
      <div className="settings-openviking-event-main">
        <div className="settings-openviking-event-title">
          <strong>{event.event_type}</strong>
          {group.count > 1 ? (
            <button
              aria-label={`${expanded ? "收起" : "展开"} ${event.event_type} 事件组`}
              className="settings-openviking-event-count"
              type="button"
              onClick={() =>
                setExpanded((value) => {
                  const nextExpanded = !value;
                  feedback.showSuccess(
                    `${nextExpanded ? "已展开" : "已收起"} ${event.event_type} 事件组`,
                  );
                  return nextExpanded;
                })
              }
            >
              ×{group.count}
            </button>
          ) : null}
        </div>
        <span>{eventSummary(event)}</span>
        <time dateTime={event.created_at ?? undefined}>{formatDateTime(event.created_at)}</time>
        {expanded ? (
          <div className="settings-openviking-event-children">
            {group.events.map((child) => (
              <div className="settings-openviking-event-child" key={child.id}>
                <span>{eventSummary(child)}</span>
                <time dateTime={child.created_at ?? undefined}>{formatDateTime(child.created_at)}</time>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <Badge text={event.outcome} outcome={event.outcome} />
    </li>
  );
}

function OpenVikingTuningCard({
  feedback,
  tuning,
  preset,
  snippet,
  onRefresh,
  requestConfirm,
}: {
  feedback: DashboardFeedback;
  tuning?: OpenVikingTuningResponse;
  preset: string;
  snippet: string;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const rows = useMemo(() => flattenTuningRows(tuning), [tuning]);
  const groups = useMemo(() => groupTuningRows(rows), [rows]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const applyMutation = useMutation({
    mutationFn: applyOpenVikingTuning,
    onError: (error) => feedback.showError(`保存调优参数失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("调优参数已保存");
    },
  });
  const presetMutation = useMutation({
    mutationFn: applyOpenVikingTuningPreset,
    onError: (error) => feedback.showError(`套用调优预设失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("调优预设已套用");
    },
  });
  const ollamaVerifyMutation = useMutation({
    mutationFn: verifyOllamaSettings,
    onError: (error) => feedback.showError(`验证 Ollama 设置失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("Ollama 设置验证完成");
    },
  });
  const mutationError =
    mutationErrorMessage(applyMutation.error) ??
    mutationErrorMessage(presetMutation.error) ??
    mutationErrorMessage(ollamaVerifyMutation.error);
  const rejectedChanges = [
    ...rejectedFromMutation(applyMutation.data),
    ...rejectedFromMutation(presetMutation.data),
  ];

  useEffect(() => {
    setDrafts(Object.fromEntries(rows.map((row) => [tuningKey(row), row.value])));
  }, [rows]);

  function handleApply(row: TuningRow, value?: string) {
    const nextValue = value ?? drafts[tuningKey(row)] ?? row.value;
    if (valuesEqual(nextValue, row.value)) {
      feedback.showSuccess("参数值没有变化，无需应用");
      return;
    }
    requestConfirm({
      confirmLabel: "确认应用",
      message: `确认将 ${tuningKey(row)} 从 ${displayValue(row.value)} 修改为 ${displayValue(nextValue)}？该操作可能影响 OpenViking 运行。`,
      onConfirm: () => {
        feedback.showSuccess("调优参数保存已提交");
        applyMutation.mutate({
          changes: [{ scope: row.scope, key: row.key, value: nextValue }],
        });
      },
      title: "确认应用调优参数",
    });
  }

  function handlePreset() {
    requestConfirm({
      confirmLabel: "确认套用",
      message: `确认套用 ${preset} 预设？这会批量修改 OpenViking 和 CodeAsk 调优参数。`,
      onConfirm: () => {
        feedback.showSuccess("调优预设套用已提交");
        presetMutation.mutate(preset);
      },
      title: "确认套用预设",
    });
  }

  return (
    <section className="surface openviking-card openviking-card-tuning" aria-label="OpenViking 调优参数">
      <TuningCardHeader
        onApplyPreset={handlePreset}
        preset={preset}
        totalCount={rows.length}
      />
      {mutationError ? <StatusError text={mutationError} /> : null}
      {rejectedChanges.map((item) => (
        <StatusError
          text={`${item.scope}.${item.key}: ${item.reason}`}
          key={`${item.scope}:${item.key}:${item.reason}`}
        />
      ))}
      <div className="settings-openviking-tuning-list">
        {groups.map(([scope, scopeRows]) => (
          <ScopeSummaryCard
            drafts={drafts}
            key={scope}
            onApply={handleApply}
            onDraftChange={(row, value) =>
              setDrafts((current) => ({ ...current, [tuningKey(row)]: value }))
            }
            rows={scopeRows}
            scope={scope}
          />
        ))}
      </div>
      <div className="settings-openviking-snippet">
        <div>
          <div className="settings-runtime-path-label">Ollama systemd snippet</div>
          <p>用于在宿主机 Ollama 服务中应用当前配置的并发参数。</p>
        </div>
        <code>{snippet || "正在读取 snippet"}</code>
        <div className="settings-openviking-snippet-actions">
          <button
            className="button button-secondary"
            type="button"
            onClick={() => copyToClipboard(snippet, "Ollama snippet", feedback)}
          >
            <Copy size={15} />
            复制
          </button>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => {
              feedback.showSuccess("Ollama 设置验证已提交");
              ollamaVerifyMutation.mutate();
            }}
          >
            验证 Ollama 设置
          </button>
          {ollamaVerifyMutation.data ? (
            <span className="settings-openviking-verify-result">
              {ollamaVerifyMutation.data.verified ? "验证通过" : "验证未通过"} · expected{" "}
              {ollamaVerifyMutation.data.expected_num_parallel} / observed{" "}
              {displayValue(ollamaVerifyMutation.data.observed_parallel)}
            </span>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function OpenVikingMetricsCard({
  status,
}: {
  status?: OpenVikingStatusResponse;
}) {
  const metrics = status?.metrics_5min;
  const collected = metrics?.collected === true;
  const notCollected = metrics?.message ?? "未采集";
  return (
    <section className="surface openviking-card openviking-card-metrics" aria-label="OpenViking 运行指标">
      <OpenVikingCardHeader
        description="5 分钟窗口内的 OpenViking 运行指标。"
        icon={<Gauge aria-hidden="true" size={16} />}
        title="运行指标"
      />
      <div className="settings-diagnostic-grid settings-diagnostic-grid-metrics">
        <Metric label="吞吐 / min" value={collected ? metrics?.throughput_per_min : notCollected} />
        <Metric label="Latency p95" value={collected ? metrics?.latency_p95_ms : notCollected} />
        <Metric label="Breaker trips" value={collected ? metrics?.breaker_trips : notCollected} />
        <Metric label="Samples" value={collected ? metrics?.latency_samples : notCollected} />
      </div>
    </section>
  );
}

function TuningCardHeader({
  onApplyPreset,
  preset,
  totalCount,
}: {
  onApplyPreset: () => void;
  preset: string;
  totalCount: number;
}) {
  return (
    <OpenVikingCardHeader
      actions={
        <button className="button button-secondary" type="button" onClick={onApplyPreset}>
          套用预设
        </button>
      }
      description={`当前推荐预设：${preset} · 共 ${totalCount} 项`}
      icon={<SlidersHorizontal aria-hidden="true" size={16} />}
      title="调优参数"
    />
  );
}

function ScopeSummaryCard({
  drafts,
  onApply,
  onDraftChange,
  rows,
  scope,
}: {
  drafts: Record<string, string>;
  onApply: (row: TuningRow, value?: string) => void;
  onDraftChange: (row: TuningRow, value: string) => void;
  rows: TuningRow[];
  scope: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <details className="tuning-scope-summary" open={open}>
      <summary
        aria-expanded={open}
        className="tuning-scope-summary-head"
        onClick={(event) => {
          event.preventDefault();
          setOpen((current) => !current);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen((current) => !current);
          }
        }}
      >
        <div className="tuning-scope-title">
          <h3>{SCOPE_LABELS[scope] ?? scope}</h3>
          <span>{open ? "正在查看此组参数" : "点击展开查看参数、推荐值和修改入口"}</span>
        </div>
        <div className="tuning-scope-actions">
          <span className="tuning-scope-pills">{rows.length} 项参数</span>
          <span className="tuning-scope-action">
            {open ? "收起参数" : "展开参数"}
            <ChevronDown aria-hidden="true" size={15} />
          </span>
        </div>
      </summary>
      <div className="tuning-advanced-table">
        <TuningTableHeader />
        {rows.map((row) => (
          <TuningParameterRow
            draftValue={drafts[tuningKey(row)] ?? row.value}
            key={tuningKey(row)}
            onApply={onApply}
            onDraftChange={(value) => onDraftChange(row, value)}
            row={row}
          />
        ))}
      </div>
    </details>
  );
}

function TuningParameterRow({
  draftValue,
  onApply,
  onDraftChange,
  row,
}: {
  draftValue: string;
  onApply: (row: TuningRow, value?: string) => void;
  onDraftChange: (value: string) => void;
  row: TuningRow;
}) {
  const key = tuningKey(row);
  const description = tuningDescription(row);
  return (
    <div className="tuning-advanced-row">
      <div className="tuning-row-label">
        <strong>{row.key}</strong>
        <span>{description.description}</span>
        <small>{description.impact}</small>
      </div>
      <input
        aria-label={`自定义值 ${key}`}
        value={draftValue}
        onChange={(event) => onDraftChange(event.target.value)}
      />
      <span>推荐 {displayValue(row.recommended)}</span>
      <button
        aria-label={`应用 ${key}`}
        className="button button-secondary"
        type="button"
        onClick={() => onApply(row, draftValue)}
      >
        应用
      </button>
    </div>
  );
}

function TuningTableHeader() {
  return (
    <div className="tuning-advanced-header" aria-hidden="true">
      <span>参数</span>
      <span>自定义值</span>
      <span>推荐值</span>
      <span>操作</span>
    </div>
  );
}

function flattenTuningRows(tuning?: OpenVikingTuningResponse): TuningRow[] {
  if (!tuning) {
    return [];
  }
  return Object.entries(tuning.scopes).flatMap(([scope, rows]) =>
    rows.map((row) => ({ ...row, scope })),
  );
}

function groupTuningRows(rows: TuningRow[]): Array<[string, TuningRow[]]> {
  const groups = new Map<string, TuningRow[]>();
  for (const row of rows) {
    groups.set(row.scope, [...(groups.get(row.scope) ?? []), row]);
  }
  return Array.from(groups.entries()).sort(([left], [right]) => {
    const order = ["openviking", "codeask", "ollama_recommend"];
    return order.indexOf(left) - order.indexOf(right);
  });
}

function tuningKey(row: Pick<TuningRow, "scope" | "key">) {
  return `${row.scope}.${row.key}`;
}

function tuningDescription(row: TuningRow) {
  return (
    TUNING_DESCRIPTIONS[tuningKey(row)] ?? {
      description: "运行参数。",
      impact: "按配置生效",
    }
  );
}

function valuesEqual(left: number | string | null | undefined, right: number | string | null | undefined) {
  return displayValue(left).trim() === displayValue(right).trim();
}

function syncProgressView(progress: unknown): { eta: string; label: string; value: number | null } {
  if (!progress || typeof progress !== "object") {
    return { value: null, label: EMPTY_VALUE, eta: EMPTY_VALUE };
  }
  const payload = progress as Record<string, unknown>;
  const total = numberFromUnknown(payload.total);
  const indexed = numberFromUnknown(payload.indexed ?? payload.completed);
  const etaSeconds = numberFromUnknown(payload.eta_seconds);

  if (total === null || total <= 0 || indexed === null) {
    return {
      value: null,
      label: EMPTY_VALUE,
      eta: etaSeconds === null ? EMPTY_VALUE : formatSeconds(etaSeconds),
    };
  }

  const value = clamp(Math.round((indexed / total) * 100), 0, 100);
  return {
    value,
    label: `${value}%`,
    eta: etaSeconds === null ? EMPTY_VALUE : formatSeconds(etaSeconds),
  };
}

function statusOutcome(status: string): "info" | "success" | "warning" | "error" {
  if (status === "failed") {
    return "error";
  }
  if (status === "indexed") {
    return "success";
  }
  if (status === "running") {
    return "warning";
  }
  return "info";
}

function collapseConsecutiveEvents(events: OpenVikingDashboardEvent[]): EventGroup[] {
  const groups: EventGroup[] = [];
  for (const event of events) {
    const last = groups.at(-1);
    if (
      last &&
      last.event.event_type === event.event_type &&
      last.event.outcome === event.outcome &&
      last.event.source_type === event.source_type
    ) {
      last.count += 1;
      last.events.push(event);
      continue;
    }
    groups.push({ count: 1, event, events: [event] });
  }
  return groups;
}

function eventSummary(event: OpenVikingDashboardEvent) {
  const payload = recordFromUnknown(event.payload);
  if (event.event_type === "tuning_change") {
    const scope = stringFromUnknown(payload?.scope) ?? event.source_type ?? "system";
    const key = stringFromUnknown(payload?.key) ?? stringFromUnknown(payload?.setting_key);
    const before =
      stringFromUnknown(payload?.previous_value) ??
      stringFromUnknown(payload?.old_value) ??
      stringFromUnknown(payload?.value_before) ??
      EMPTY_VALUE;
    const after =
      stringFromUnknown(payload?.value) ??
      stringFromUnknown(payload?.new_value) ??
      stringFromUnknown(payload?.value_after) ??
      EMPTY_VALUE;
    return `${scope}${key ? `.${key}` : ""}: ${before} → ${after}`;
  }
  if (payload?.count !== undefined) {
    return `${event.source_type ?? "system"} · count=${String(payload.count)}`;
  }
  if (payload?.job_id !== undefined) {
    return `${event.source_type ?? "system"} · job=${String(payload.job_id)}`;
  }
  const readableName =
    stringFromUnknown(payload?.name) ??
    stringFromUnknown(payload?.title) ??
    readablePathFromPayload(payload);
  if (readableName) {
    return `${event.source_type ?? "system"} · ${readableName}`;
  }
  if (event.source_id) {
    return `${event.source_type ?? "system"} · ${event.source_id}`;
  }
  if (payload) {
    const pairs = Object.entries(payload)
      .slice(0, 3)
      .map(([key, value]) => `${key}=${String(value)}`);
    if (pairs.length > 0) {
      return pairs.join(" · ");
    }
  }
  return event.source_type ?? "system";
}

function readablePathFromPayload(payload: Record<string, unknown> | null) {
  const featureSlug = stringFromUnknown(payload?.feature_slug);
  const relativePath = stringFromUnknown(payload?.relative_path);
  if (featureSlug && relativePath) {
    return `${featureSlug}/${relativePath}`;
  }
  return null;
}

function recordFromUnknown(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function stringFromUnknown(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function formatDateTime(value: string | null) {
  if (!value) {
    return EMPTY_VALUE;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  }).format(date);
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function formatSeconds(value: number) {
  return `${Math.max(0, Math.round(value))}s`;
}

function mutationErrorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return messageFromApiError(error);
}

function rejectedFromMutation(data?: OpenVikingTuningApplyResponse) {
  return data?.rejected ?? [];
}

function displayValue(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return EMPTY_VALUE;
  }
  return String(value);
}

function Metric({ label, value }: { label: string; value: number | string | null | undefined }) {
  return (
    <div className="settings-diagnostic-item">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  );
}

function copyToClipboard(value: string, label: string, feedback: DashboardFeedback) {
  if (!navigator.clipboard) {
    feedback.showError("当前浏览器不支持剪贴板复制", { title: "复制失败" });
    return;
  }
  void navigator.clipboard
    .writeText(value)
    .then(() => feedback.showSuccess(`${label}已复制`))
    .catch((error: unknown) =>
      feedback.showError(`复制${label}失败：${messageFromApiError(error)}`, { title: "复制失败" }),
    );
}

function PathBlock({
  feedback,
  label,
  value,
}: {
  feedback: DashboardFeedback;
  label: string;
  value?: string | null;
}) {
  if (!value) {
    return null;
  }
  return (
    <div className="settings-runtime-path-item">
      <div className="settings-runtime-path-label">{label}</div>
      <code>{value}</code>
      <div className="settings-runtime-path-action">
        <button
          aria-label={`复制 ${label}`}
          className="settings-runtime-copy-button"
          type="button"
          onClick={() => copyToClipboard(value, label, feedback)}
        >
          <Copy size={14} />
          复制
        </button>
      </div>
    </div>
  );
}

function StatusError({ text }: { text: string }) {
  return (
    <div className="settings-status-error" role="alert">
      <AlertTriangle aria-hidden="true" size={16} />
      <span>{text}</span>
    </div>
  );
}

function Badge({
  text,
  outcome = "info",
}: {
  text: string;
  outcome?: "info" | "success" | "warning" | "error";
}) {
  return (
    <span className="settings-openviking-badge" data-outcome={outcome}>
      {text}
    </span>
  );
}
