import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Database,
  Gauge,
  ListChecks,
  RotateCcw,
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
  rollbackOpenVikingTuning,
  switchEmbeddingModel,
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

type TuningRow = OpenVikingTuningItem & { scope: string };
type EventGroup = {
  count: number;
  event: OpenVikingDashboardEvent;
};

const EMPTY_VALUE = "—";
const EVENT_PAGE_SIZE = 10;
const JOB_PAGE_SIZE = 6;

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
    impact: "调度项后续接入",
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
  const [eventOutcome, setEventOutcome] = useState("");
  const [eventType, setEventType] = useState("");
  const [eventBeforeId, setEventBeforeId] = useState<number | undefined>();
  const [eventItems, setEventItems] = useState<OpenVikingDashboardEvent[]>([]);
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
  const jobsQuery = useQuery({
    queryKey: ["admin-openviking-sync-jobs"],
    queryFn: listOpenVikingSyncJobs,
    refetchInterval: 5000,
  });
  const eventsQuery = useQuery({
    queryKey: ["admin-openviking-events", eventOutcome, eventType, eventBeforeId],
    queryFn: () =>
      listOpenVikingEvents({
        eventType: eventType || undefined,
        outcome: eventOutcome || undefined,
        beforeId: eventBeforeId,
        limit: EVENT_PAGE_SIZE,
      }),
    refetchInterval: 5000,
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

  useEffect(() => {
    const payload = eventsQuery.data;
    if (!payload) {
      return;
    }
    if (!eventBeforeId) {
      setEventItems(payload.items);
      return;
    }
    setEventItems((current) => {
      const seen = new Set(current.map((event) => event.id));
      return [
        ...current,
        ...payload.items.filter((event) => !seen.has(event.id)),
      ];
    });
  }, [eventsQuery.data, eventBeforeId]);

  function handleOutcomeChange(value: string) {
    setEventItems([]);
    setEventBeforeId(undefined);
    setEventOutcome(value);
  }

  function handleEventTypeChange(value: string) {
    setEventItems([]);
    setEventBeforeId(undefined);
    setEventType(value);
  }

  const jobs = jobsQuery.data?.items ?? [];

  return (
    <div className="openviking-dashboard">
      <div className="settings-openviking-grid">
        <OpenVikingHealthCard
          status={statusQuery.data}
          loading={statusQuery.isLoading}
          error={statusQuery.isError ? "读取 OpenViking 状态失败" : null}
        />
        <OpenVikingEmbeddingCard
          embedding={embeddingQuery.data}
          candidates={candidatesQuery.data?.items ?? []}
          loading={embeddingQuery.isLoading}
          onRefresh={refresh}
        />
        <OpenVikingSyncJobsCard jobs={jobs} onRefresh={refresh} />
        <OpenVikingEventStream
          events={eventItems}
          outcome={eventOutcome}
          eventType={eventType}
          onOutcomeChange={handleOutcomeChange}
          onEventTypeChange={handleEventTypeChange}
          hasNext={Boolean(eventsQuery.data?.next_before_id)}
          onLoadMore={() => setEventBeforeId(eventsQuery.data?.next_before_id ?? undefined)}
        />
        <OpenVikingMetricsCard status={statusQuery.data} />
        <OpenVikingTuningCard
          tuning={tuningQuery.data}
          preset={presetQuery.data?.preset ?? tuningQuery.data?.preset ?? EMPTY_VALUE}
          snippet={snippetQuery.data?.snippet ?? ""}
          onRefresh={refresh}
        />
      </div>
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
  status,
  loading,
  error,
}: {
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
            <PathBlock label="配置文件" value={status.config_file} />
            <PathBlock label="工作目录" value={status.workspace_path} />
            <PathBlock label="日志文件" value={status.log_file} />
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
  loading,
  onRefresh,
}: {
  embedding?: OpenVikingEmbeddingResponse;
  candidates: OpenVikingEmbeddingCandidate[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const [selectedModel, setSelectedModel] = useState("");
  const switchMutation = useMutation({
    mutationFn: switchEmbeddingModel,
    onSuccess: onRefresh,
  });
  const rebuildMutation = useMutation({
    mutationFn: rebuildEmbedding,
    onSuccess: onRefresh,
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
    const confirmed = window.confirm("切换 Embedding 模型会清理索引并触发全量重建。是否继续？");
    if (!confirmed) {
      return;
    }
    switchMutation.mutate({
      provider: selectedCandidate.provider,
      base_url: selectedCandidate.base_url,
      model: selectedCandidate.model,
      dimension: embedding.dimension,
      max_concurrent: embedding.max_concurrent,
    });
  }

  function handleRebuildEmbedding() {
    if (!window.confirm("这会重新构建 OpenViking 语义索引，过程中检索可能降级。是否继续？")) {
      return;
    }
    rebuildMutation.mutate();
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
  jobs,
  onRefresh,
}: {
  jobs: OpenVikingSyncJob[];
  onRefresh: () => void;
}) {
  const [showIndexed, setShowIndexed] = useState(false);
  const [visibleCount, setVisibleCount] = useState(JOB_PAGE_SIZE);
  const retryMutation = useMutation({ mutationFn: retrySyncJob, onSuccess: onRefresh });
  const retryFailedMutation = useMutation({ mutationFn: retryFailedSyncJobs, onSuccess: onRefresh });
  const resyncMutation = useMutation({ mutationFn: resyncOpenViking, onSuccess: onRefresh });
  const rebuildMutation = useMutation({ mutationFn: rebuildOpenVikingIndex, onSuccess: onRefresh });
  const mutationError =
    mutationErrorMessage(retryMutation.error) ??
    mutationErrorMessage(retryFailedMutation.error) ??
    mutationErrorMessage(resyncMutation.error) ??
    mutationErrorMessage(rebuildMutation.error);
  const counts = jobStatusCounts(jobs);
  const filteredJobs = showIndexed ? jobs : jobs.filter((job) => job.status !== "indexed");
  const visibleJobs = filteredJobs.slice(0, visibleCount);

  useEffect(() => {
    setVisibleCount(JOB_PAGE_SIZE);
  }, [showIndexed, jobs.length]);

  function handleRebuild() {
    if (!window.confirm("重排同步队列会将已发布知识重新加入同步队列。是否继续？")) {
      return;
    }
    rebuildMutation.mutate();
  }

  return (
    <section className="surface openviking-card openviking-card-sync" aria-label="OpenViking 同步任务">
      <OpenVikingCardHeader
        actions={
          <>
            <button className="button button-secondary" type="button" onClick={() => retryFailedMutation.mutate()}>
              重试失败
            </button>
            <button className="button button-secondary" type="button" onClick={() => resyncMutation.mutate({})}>
              重新同步
            </button>
            <button className="button button-danger" type="button" onClick={handleRebuild}>
              重排同步队列
            </button>
            {counts.indexed > 0 ? (
              <button className="button button-quiet" type="button" onClick={() => setShowIndexed((value) => !value)}>
                {showIndexed ? "隐藏 indexed" : `显示 indexed (${counts.indexed})`}
              </button>
            ) : null}
          </>
        }
        description="队列、失败重试和重新排队操作入口。"
        icon={<ListChecks aria-hidden="true" size={16} />}
        title="同步任务"
      />
      <div className="settings-openviking-job-summary">
        <StatusPill label="pending" value={String(counts.pending)} />
        <StatusPill label="running" value={String(counts.running)} />
        <StatusPill label="failed" value={String(counts.failed)} tone={counts.failed ? "error" : "info"} />
        <StatusPill label="indexed" value={String(counts.indexed)} tone="success" />
      </div>
      <p className="settings-openviking-muted">
        重排同步队列会重新安排已发布 Wiki 和已验证报告同步；不会切换 Embedding 模型。
      </p>
      <ul className="data-list settings-config-list settings-openviking-job-list">
        {visibleJobs.map((job) => (
          <SyncJobItem
            job={job}
            key={job.id}
            onRetry={() => retryMutation.mutate(job.id)}
          />
        ))}
      </ul>
      {filteredJobs.length > visibleJobs.length ? (
        <button
          className="button button-secondary settings-openviking-load-more"
          type="button"
          onClick={() => setVisibleCount((value) => value + JOB_PAGE_SIZE)}
        >
          加载更多
        </button>
      ) : null}
      {mutationError ? <StatusError text={mutationError} /> : null}
      {filteredJobs.length === 0 ? (
        <p className="empty-note">
          {counts.indexed > 0 ? "当前只剩已索引任务，默认已折叠。" : "暂无同步任务"}
        </p>
      ) : null}
    </section>
  );
}

function SyncJobItem({ job, onRetry }: { job: OpenVikingSyncJob; onRetry: () => void }) {
  const progress = syncProgressView(job.progress);
  return (
    <li className="settings-openviking-job-row">
      <div className="settings-openviking-row-main">
        <strong>{job.source_type}</strong>
        <span>{job.source_id}</span>
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
  outcome,
  eventType,
  onOutcomeChange,
  onEventTypeChange,
  hasNext,
  onLoadMore,
}: {
  events: OpenVikingDashboardEvent[];
  outcome: string;
  eventType: string;
  onOutcomeChange: (value: string) => void;
  onEventTypeChange: (value: string) => void;
  hasNext: boolean;
  onLoadMore: () => void;
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
          <EventItem group={group} key={`${group.event.id}:${group.count}`} />
        ))}
      </ul>
      {events.length === 0 ? <p className="empty-note">暂无 OpenViking 事件</p> : null}
      {hasNext ? (
        <button className="button button-secondary settings-openviking-load-more" type="button" onClick={onLoadMore}>
          加载更多
        </button>
      ) : null}
    </section>
  );
}

function EventItem({ group }: { group: EventGroup }) {
  const { event } = group;
  return (
    <li className="settings-openviking-row" data-outcome={event.outcome}>
      <div className="settings-openviking-event-main">
        <div className="settings-openviking-event-title">
          <strong>{event.event_type}</strong>
          {group.count > 1 ? <span className="settings-openviking-event-count">×{group.count}</span> : null}
        </div>
        <span>{eventSummary(event)}</span>
        <time dateTime={event.created_at ?? undefined}>{formatDateTime(event.created_at)}</time>
      </div>
      <Badge text={event.outcome} outcome={event.outcome} />
    </li>
  );
}

function OpenVikingTuningCard({
  tuning,
  preset,
  snippet,
  onRefresh,
}: {
  tuning?: OpenVikingTuningResponse;
  preset: string;
  snippet: string;
  onRefresh: () => void;
}) {
  const rows = useMemo(() => flattenTuningRows(tuning), [tuning]);
  const groups = useMemo(() => groupTuningRows(rows), [rows]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const applyMutation = useMutation({ mutationFn: applyOpenVikingTuning, onSuccess: onRefresh });
  const rollbackMutation = useMutation({ mutationFn: rollbackOpenVikingTuning, onSuccess: onRefresh });
  const presetMutation = useMutation({
    mutationFn: applyOpenVikingTuningPreset,
    onSuccess: onRefresh,
  });
  const mutationError =
    mutationErrorMessage(applyMutation.error) ??
    mutationErrorMessage(rollbackMutation.error) ??
    mutationErrorMessage(presetMutation.error);
  const rejectedChanges = [
    ...rejectedFromMutation(applyMutation.data),
    ...rejectedFromMutation(rollbackMutation.data),
    ...rejectedFromMutation(presetMutation.data),
  ];

  useEffect(() => {
    setDrafts(Object.fromEntries(rows.map((row) => [tuningKey(row), row.value])));
  }, [rows]);

  function handleApply(row: TuningRow) {
    applyMutation.mutate({
      changes: [{ scope: row.scope, key: row.key, value: drafts[tuningKey(row)] ?? row.value }],
    });
  }

  function handlePreset() {
    if (!window.confirm("套用预设会批量修改 OpenViking 和 CodeAsk 调优参数。是否继续？")) {
      return;
    }
    presetMutation.mutate(preset);
  }

  return (
    <section className="surface openviking-card openviking-card-tuning" aria-label="OpenViking 调优参数">
      <OpenVikingCardHeader
        actions={
          <button className="button button-secondary" type="button" onClick={handlePreset}>
            套用预设
          </button>
        }
        description={`当前推荐预设：${preset}`}
        icon={<SlidersHorizontal aria-hidden="true" size={16} />}
        title="调优参数"
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
          <section className="settings-openviking-scope-section" key={scope}>
            <div className="settings-openviking-scope-heading">
              <h3>{SCOPE_LABELS[scope] ?? scope}</h3>
            </div>
            {scopeRows.map((row) => {
              const key = tuningKey(row);
              const draftValue = drafts[key] ?? row.value;
              const differsFromRecommended = valueDiffersFromRecommended(draftValue, row.recommended);
              const description = TUNING_DESCRIPTIONS[key] ?? {
                description: "运行参数。",
                impact: "按配置生效",
              };
              return (
                <div
                  className="settings-openviking-tuning-row"
                  data-recommendation={differsFromRecommended ? "changed" : "aligned"}
                  key={key}
                >
                  <div className="settings-openviking-tuning-meta">
                    <strong>{row.key}</strong>
                    <span>{description.description}</span>
                    <small>{description.impact}</small>
                  </div>
                  <label className="settings-openviking-field settings-openviking-tuning-field">
                    <span>当前值</span>
                    <input
                      aria-label={key}
                      value={draftValue}
                      onChange={(event) =>
                        setDrafts((current) => ({ ...current, [key]: event.target.value }))
                      }
                    />
                  </label>
                  <div className="settings-openviking-recommended">
                    <span>推荐值</span>
                    <strong>{displayValue(row.recommended)}</strong>
                    {differsFromRecommended ? (
                      <small className="settings-openviking-recommendation-delta">偏离推荐</small>
                    ) : null}
                  </div>
                  <div className="settings-openviking-tuning-actions">
                    <button
                      aria-label={`应用 ${key}`}
                      className="button button-secondary"
                      type="button"
                      onClick={() => handleApply(row)}
                    >
                      应用
                    </button>
                    <button
                      aria-label={`回滚 ${key}`}
                      className="button button-quiet"
                      type="button"
                      onClick={() => rollbackMutation.mutate({ scope: row.scope, key: row.key })}
                      disabled={!row.previous_value}
                    >
                      <RotateCcw size={15} />
                      回滚
                    </button>
                  </div>
                </div>
              );
            })}
          </section>
        ))}
      </div>
      <div className="settings-openviking-snippet">
        <div>
          <div className="settings-runtime-path-label">Ollama systemd snippet</div>
          <p>用于在宿主机 Ollama 服务中应用当前配置的并发参数。</p>
        </div>
        <code>{snippet || "正在读取 snippet"}</code>
        <button
          className="button button-secondary"
          type="button"
          onClick={() => void navigator.clipboard?.writeText(snippet)}
        >
          <Copy size={15} />
          复制
        </button>
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
      </div>
    </section>
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

function valueDiffersFromRecommended(
  value: number | string | null | undefined,
  recommended: number | string | null | undefined,
) {
  if (recommended === null || recommended === undefined || recommended === "") {
    return false;
  }
  return displayValue(value).trim() !== displayValue(recommended).trim();
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

function jobStatusCounts(jobs: OpenVikingSyncJob[]) {
  return jobs.reduce(
    (counts, job) => {
      counts[job.status] = (counts[job.status] ?? 0) + 1;
      return counts;
    },
    { cancelled: 0, failed: 0, indexed: 0, pending: 0, running: 0 } as Record<string, number>,
  );
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
      continue;
    }
    groups.push({ count: 1, event });
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
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
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

function PathBlock({ label, value }: { label: string; value?: string | null }) {
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
          onClick={() => void navigator.clipboard?.writeText(value)}
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
