import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Copy,
  Database,
  Eye,
  LoaderCircle,
  ListChecks,
  SlidersHorizontal,
  Stethoscope,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import {
  applyEmbeddingConfig,
  applyOpenVikingTuning,
  applyOpenVikingTuningPreset,
  applyVLMConfig,
  disableVLMConfig,
  getOpenVikingEmbedding,
  getOpenVikingStatus,
  getOpenVikingSyncJobsSummary,
  getOpenVikingTuning,
  getOpenVikingVLM,
  getTuningPreset,
  listEmbeddingCandidates,
  listOpenVikingEvents,
  listOpenVikingSyncJobs,
  rebuildEmbedding,
  rebuildOpenVikingIndex,
  resyncOpenViking,
  retryFailedSyncJobs,
  retrySyncJob,
  testEmbeddingConfig,
  testVLMConfig,
} from "../../lib/api";
import type {
  OpenVikingDashboardEvent,
  OpenVikingDoctorCheck,
  OpenVikingDoctorReport,
  OpenVikingEmbeddingApplyRequest,
  OpenVikingEmbeddingCandidate,
  OpenVikingEmbeddingResponse,
  OpenVikingEmbeddingSecretRef,
  OpenVikingStatusResponse,
  OpenVikingSyncJob,
  OpenVikingTuningApplyResponse,
  OpenVikingTuningItem,
  OpenVikingTuningResponse,
  OpenVikingVLMApplyRequest,
  OpenVikingVLMResponse,
} from "../../types/api";
import { useAppFeedback, type AppFeedbackToastTone } from "../feedback/AppFeedback";
import { copyTextToClipboard } from "../session/session-clipboard";
import { SwitchControl } from "./SwitchControl";
import { messageFromApiError } from "./settings-utils";

type TuningRow = OpenVikingTuningItem & { scope: string };
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
  showToast: (message: string, options?: { tone?: AppFeedbackToastTone }) => void;
};
type DashboardConfirm = (request: DashboardConfirmRequest) => void;

const EMPTY_VALUE = "—";
const DEFAULT_EVENT_PAGE_SIZE = 5;
const EVENT_PAGE_SIZE_OPTIONS = [5, 10, 20, 50];
const JOB_PAGE_SIZE = 5;

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

const EVENT_LABELS: Record<string, string> = {
  embedding_model_switched: "向量模型切换",
  embedding_rebuild_requested: "向量重建已请求",
  manual_rebuild_index: "手动重建索引",
  manual_resync: "手动重新同步",
  manual_retry: "手动重试",
  manual_retry_failed: "重试全部失败任务",
  ollama_recovery: "Ollama 已恢复",
  ollama_settings_verified: "Ollama 设置已验证",
  openviking_breaker_tripped: "OpenViking 熔断触发",
  openviking_health_failed: "OpenViking 健康检查失败",
  openviking_restart_detected: "OpenViking 进程重启",
  repo_refresh_summary: "仓库刷新汇总",
  repo_synced: "仓库已同步",
  scheduled_refresh_summary: "定时同步汇总",
  sync_job_enqueued: "同步任务已入队",
  sync_job_failed: "同步任务失败",
  tuning_change: "调优参数变更",
  vlm_config_changed: "VLM 配置变更",
};

const EMBEDDING_PROVIDER_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "local", label: "Local（内置 GGUF）" },
  { value: "ollama", label: "Ollama" },
  { value: "openai", label: "OpenAI" },
  { value: "azure", label: "Azure" },
  { value: "volcengine", label: "VolcEngine" },
  { value: "vikingdb", label: "VikingDB" },
  { value: "jina", label: "Jina" },
  { value: "gemini", label: "Gemini" },
  { value: "voyage", label: "Voyage" },
  { value: "dashscope", label: "DashScope" },
  { value: "minimax", label: "MiniMax" },
  { value: "cohere", label: "Cohere" },
  { value: "litellm", label: "LiteLLM" },
];

const VLM_PROVIDER_SUGGESTIONS: ReadonlyArray<string> = [
  "volcengine",
  "openai",
  "azure",
  "kimi",
  "glm",
  "litellm",
  "openai-codex",
];

const EMBEDDING_PROVIDER_DEFAULTS: Record<string, { model: string; dimension: number | null }> = {
  local: { model: "bge-small-zh-v1.5-f16", dimension: 512 },
  ollama: { model: "bge-m3", dimension: 1024 },
};

const CLOUD_EMBEDDING_PROVIDERS = new Set([
  "openai",
  "azure",
  "volcengine",
  "jina",
  "gemini",
  "voyage",
  "dashscope",
  "minimax",
  "cohere",
  "litellm",
]);

const OUTCOME_LABELS: Record<OpenVikingDashboardEvent["outcome"], string> = {
  error: "错误",
  info: "信息",
  success: "成功",
  warning: "警告",
};

const SYNC_STATUS_LABELS: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  failed: "失败",
  cancelled: "已停止重试",
  indexed: "已索引",
};

const SYNC_SOURCE_LABELS: Record<string, string> = {
  manual_text: "手动内容",
  report: "问题报告",
  repo: "代码仓",
  wiki_doc: "Wiki 文档",
};

type EventView = "all" | "important";

export function OpenVikingDashboard() {
  const queryClient = useQueryClient();
  const feedback = useAppFeedback();
  const [confirmRequest, setConfirmRequest] = useState<DashboardConfirmRequest | null>(null);
  const [eventOutcome, setEventOutcome] = useState("");
  const [eventPage, setEventPage] = useState(1);
  const [eventPageSize, setEventPageSize] = useState(DEFAULT_EVENT_PAGE_SIZE);
  const [eventType, setEventType] = useState("");
  const [eventView, setEventView] = useState<EventView>("important");
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
  const eventsQuery = useQuery({
    queryKey: [
      "admin-openviking-events",
      eventView,
      eventOutcome,
      eventType,
      eventPage,
      eventPageSize,
    ],
    queryFn: () =>
      listOpenVikingEvents({
        eventType: eventType || undefined,
        outcome: eventOutcome || undefined,
        limit: eventPageSize,
        page: eventPage,
        view: eventView,
      }),
    refetchInterval: eventPage === 1 ? 5000 : false,
  });
  const embeddingQuery = useQuery({
    queryKey: ["admin-openviking-embedding"],
    queryFn: getOpenVikingEmbedding,
  });
  const candidatesQuery = useQuery({
    queryKey: ["admin-openviking-embedding-candidates"],
    queryFn: () => listEmbeddingCandidates(),
  });
  const vlmQuery = useQuery({
    queryKey: ["admin-openviking-vlm"],
    queryFn: getOpenVikingVLM,
  });
  const tuningQuery = useQuery({
    queryKey: ["admin-openviking-tuning"],
    queryFn: getOpenVikingTuning,
  });
  const presetQuery = useQuery({
    queryKey: ["admin-openviking-tuning-preset"],
    queryFn: getTuningPreset,
  });

  const events = eventsQuery.data?.items ?? [];
  const eventTypeOptions = eventsQuery.data?.event_types ?? [];
  const eventTotal = eventsQuery.data?.total ?? 0;
  const eventTotalPages = Math.max(1, eventsQuery.data?.total_pages ?? eventPage);

  useEffect(() => {
    if (eventsQuery.data && eventPage > eventTotalPages) {
      setEventPage(eventTotalPages);
    }
  }, [eventPage, eventTotalPages, eventsQuery.data]);

  function handleOutcomeChange(value: string) {
    resetEventPagination();
    setEventOutcome(value);
  }

  function handleEventViewChange(value: EventView) {
    resetEventPagination();
    setEventView(value);
  }

  function handleEventTypeChange(value: string) {
    resetEventPagination();
    setEventType(value);
  }

  function resetEventPagination() {
    setEventPage(1);
  }

  function handleNextEventPage() {
    setEventPage((current) => Math.min(eventTotalPages, current + 1));
  }

  function handlePreviousEventPage() {
    setEventPage((current) => Math.max(1, current - 1));
  }

  function handleEventPageSizeChange(value: number) {
    setEventPageSize(value);
    setEventPage(1);
  }

  function handleEventPageJump(value: number) {
    if (!Number.isFinite(value)) {
      return;
    }
    setEventPage(Math.max(1, Math.min(eventTotalPages, Math.trunc(value))));
  }

  return (
    <div className="openviking-dashboard">
      <OpenVikingStatusBand
        status={statusQuery.data}
        feedback={feedback}
        loading={statusQuery.isLoading}
        error={statusQuery.isError ? "读取 OpenViking 状态失败" : null}
      />
      <div className="ov-ops-grid">
        <OpenVikingSyncJobsCard
          feedback={feedback}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
        <OpenVikingEventStream
          events={events}
          eventTypeOptions={eventTypeOptions}
          feedback={feedback}
          hasNext={eventPage < eventTotalPages}
          hasPrevious={eventPage > 1}
          isLoading={eventsQuery.isLoading}
          outcome={eventOutcome}
          eventType={eventType}
          eventView={eventView}
          onRefresh={refresh}
          onOutcomeChange={handleOutcomeChange}
          onEventTypeChange={handleEventTypeChange}
          onEventViewChange={handleEventViewChange}
          onNextPage={handleNextEventPage}
          onPageJump={handleEventPageJump}
          onPageSizeChange={handleEventPageSizeChange}
          onPreviousPage={handlePreviousEventPage}
          pageNumber={eventPage}
          pageSize={eventPageSize}
          pageSizeOptions={EVENT_PAGE_SIZE_OPTIONS}
          requestConfirm={setConfirmRequest}
          total={eventTotal}
          totalPages={eventTotalPages}
        />
      </div>
      <div className="ov-config-grid">
        <OpenVikingEmbeddingCard
          embedding={embeddingQuery.data}
          candidates={candidatesQuery.data?.items ?? []}
          configuredSecrets={candidatesQuery.data?.configured_secrets ?? []}
          feedback={feedback}
          loading={embeddingQuery.isLoading}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
        <OpenVikingVLMCard
          vlm={vlmQuery.data}
          feedback={feedback}
          loading={vlmQuery.isLoading}
          onRefresh={refresh}
          requestConfirm={setConfirmRequest}
        />
      </div>
      <OpenVikingTuningCard
        feedback={feedback}
        tuning={tuningQuery.data}
        preset={presetQuery.data?.preset ?? tuningQuery.data?.preset ?? EMPTY_VALUE}
        onRefresh={refresh}
        requestConfirm={setConfirmRequest}
      />
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
  onClick,
  selected = false,
  tone = "info",
  value,
}: {
  label: string;
  onClick?: () => void;
  selected?: boolean;
  tone?: "info" | "success" | "warning" | "error";
  value: string;
}) {
  return (
    <button
      aria-label={`按${label}筛选`}
      aria-pressed={selected}
      className="ov-filter-chip"
      data-selected={selected ? "true" : undefined}
      data-tone={tone}
      type="button"
      onClick={onClick}
    >
      <span aria-hidden="true" className="ov-filter-dot" />
      <span className="ov-filter-label">{label}</span>
      <strong className="console-mono">{value}</strong>
    </button>
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

function OpenVikingStatusBand({
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
  const healthy = running && !(status?.degraded ?? false);
  const stateLabel = healthy ? "运行中" : running ? "降级运行" : "未运行";
  const stateNote = healthy
    ? "语义检索在线；偶发异常会进入降级，用户会话保持可用。"
    : running
      ? "进程在线但健康探针异常，检索能力受限，建议展开下方诊断。"
      : "进程未运行，语义检索不可用，Wiki 搜索已回退到 SQL。";
  const indexing = status?.indexing;
  const metrics = status?.metrics_5min;
  const phaseActive =
    indexing != null && indexing.phase !== "idle" && indexing.phase !== "indexed";
  const progress = indexing?.progress_percent ?? null;
  const indeterminate = phaseActive && progress === null;

  return (
    <section
      className="surface opencode-hero ov-status-band"
      data-running={healthy ? "true" : "false"}
      aria-label="OpenViking 健康状态"
    >
      <div className="opencode-hero-head">
        <span className="opencode-signal" data-running={healthy ? "true" : "false"}>
          <span className="opencode-signal-ring" aria-hidden="true" />
          <span className="opencode-signal-core">
            <Database aria-hidden="true" size={20} />
          </span>
        </span>
        <div className="opencode-hero-text">
          <span className="opencode-hero-kicker">OpenViking 语义服务</span>
          <strong>{loading && !status ? "读取中…" : stateLabel}</strong>
          <p>{loading && !status ? "正在读取 OpenViking 状态。" : stateNote}</p>
        </div>
        {indexing ? (
          <span className="ov-activity-badge" data-tone={indexingPhaseTone(indexing.phase)}>
            {phaseActive ? (
              <LoaderCircle aria-hidden="true" className="ov-activity-spin" size={13} />
            ) : (
              <CheckCircle2 aria-hidden="true" size={13} />
            )}
            <span>{indexingPhaseLabel(indexing.phase)}</span>
            {indexing.eta_label ? <small>· 预计 {indexing.eta_label}</small> : null}
          </span>
        ) : null}
      </div>

      {error ? <StatusError text={error} /> : null}

      {phaseActive ? (
        <div className="ov-hero-progress" data-indeterminate={indeterminate ? "true" : "false"}>
          <div className="ov-hero-progress-track">
            <div
              className="ov-hero-progress-fill"
              style={indeterminate ? undefined : { width: `${progress ?? 0}%` }}
            />
          </div>
          <small>
            {indeterminate
              ? "目录级任务已提交，embedding 队列处理中，当前阶段暂无精确百分比。"
              : `索引构建 ${progress}%`}
            {indexing?.items_per_minute != null ? ` · ${indexing.items_per_minute}/min` : ""}
          </small>
        </div>
      ) : null}

      {status ? (
        <div className="ov-metric-groups">
          <div className="ov-metric-group">
            <span className="ov-metric-group-label">服务身份</span>
            <div className="opencode-chip-strip">
              <HeroChip
                label="健康探针"
                tone={status.health?.healthy ? "ok" : "err"}
                value={status.health?.healthy ? "healthy" : "degraded"}
              />
              <HeroChip label="端口" mono value={displayValue(status.port)} />
              <HeroChip label="PID" mono value={displayValue(status.pid)} />
              <HeroChip label="版本" mono value={displayValue(status.version)} />
              <HeroChip label="模型后端" mono value={modelBackendValue(status)} />
              {hasConfiguredOllamaDependency(status) ? (
                <HeroChip
                  label="Ollama"
                  tone={status.ollama.model_available ? "ok" : "err"}
                  value={status.ollama.model_available ? "ready" : "missing"}
                />
              ) : null}
            </div>
          </div>
          <div className="ov-metric-group">
            <span className="ov-metric-group-label">运行指标 · 5min</span>
            <div className="opencode-chip-strip">
              <HeroChip
                label="已索引特性"
                value={`${indexing?.sync_jobs?.indexed ?? 0}/${indexing?.sync_jobs?.total ?? 0}`}
              />
              <HeroChip label="吞吐 / min" mono value={displayValue(metrics?.throughput_per_min)} />
              <HeroChip
                label="Latency p95"
                mono
                value={metrics?.latency_p95_ms != null ? `${metrics.latency_p95_ms}ms` : (metrics?.message ?? "未采集")}
              />
              <HeroChip label="Breaker trips" mono value={displayValue(metrics?.breaker_trips)} />
            </div>
          </div>
        </div>
      ) : null}

      {status ? (
        <details className="ov-hero-details">
          <summary>
            <span>诊断与运行路径</span>
            <ChevronDown aria-hidden="true" size={15} />
          </summary>
          <div className="ov-hero-details-body">
            {status.doctor ? (
              <OpenVikingDoctorPanel
                doctor={status.doctor}
                ollamaConfigured={hasConfiguredOllamaDependency(status)}
                vlmEnabled={status.vlm?.enabled ?? false}
              />
            ) : null}
            <div className="opencode-paths">
              <PathRow feedback={feedback} label="配置文件" value={status.config_file} />
              <PathRow feedback={feedback} label="工作目录" value={status.workspace_path} />
              <PathRow feedback={feedback} label="日志文件" value={status.log_file} />
            </div>
            {status.last_error ? <StatusError text={status.last_error} /> : null}
            {status.health?.error ? <StatusError text={status.health.error} /> : null}
            {status.ollama?.error ? <StatusError text={status.ollama.error} /> : null}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function HeroChip({
  label,
  mono,
  tone,
  value,
}: {
  label: string;
  mono?: boolean;
  tone?: "ok" | "err";
  value: string;
}) {
  return (
    <div className="opencode-chip" data-tone={tone}>
      <span className="opencode-chip-label">{label}</span>
      <strong className={mono ? "console-mono" : undefined}>{value}</strong>
    </div>
  );
}

function PathRow({
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
    <div className="opencode-path-item">
      <span className="opencode-path-label">{label}</span>
      <code className="console-mono">{value}</code>
      <button
        aria-label={`复制 ${label}`}
        className="opencode-copy-button"
        type="button"
        onClick={() => copyToClipboard(value, label, feedback)}
      >
        <Copy aria-hidden="true" size={13} />
        复制
      </button>
    </div>
  );
}

interface EmbeddingFormState {
  provider: string;
  base_url: string;
  model: string;
  dimension: string;
  max_concurrent: string;
  input: string;
  api_key: string;
  ak: string;
  sk: string;
  region: string;
  host: string;
}

const EMPTY_EMBEDDING_FORM: EmbeddingFormState = {
  provider: "local",
  base_url: "",
  model: "bge-small-zh-v1.5-f16",
  dimension: "512",
  max_concurrent: "1",
  input: "text",
  api_key: "",
  ak: "",
  sk: "",
  region: "",
  host: "",
};

function embeddingFormFromResponse(embedding: OpenVikingEmbeddingResponse): EmbeddingFormState {
  return {
    provider: embedding.provider,
    base_url: embedding.base_url ?? "",
    model: embedding.model,
    dimension: embedding.dimension != null ? String(embedding.dimension) : "",
    max_concurrent: String(embedding.max_concurrent),
    input: embedding.input ?? "text",
    api_key: "",
    ak: "",
    sk: "",
    region: "",
    host: "",
  };
}

function buildEmbeddingApply(form: EmbeddingFormState): OpenVikingEmbeddingApplyRequest {
  const provider = form.provider;
  const payload: OpenVikingEmbeddingApplyRequest = {
    provider,
    model: form.model.trim(),
    max_concurrent: toPositiveInt(form.max_concurrent, 1),
    input: form.input.trim() || "text",
  };
  const dimension = toIntOrNull(form.dimension);
  if (dimension !== null) {
    payload.dimension = dimension;
  }
  if ((provider === "ollama" || CLOUD_EMBEDDING_PROVIDERS.has(provider)) && form.base_url.trim()) {
    payload.base_url = form.base_url.trim();
  }
  if (CLOUD_EMBEDDING_PROVIDERS.has(provider) && form.api_key.trim()) {
    payload.api_key = form.api_key.trim();
  }
  if (provider === "vikingdb") {
    const extra: Record<string, unknown> = {};
    if (form.ak.trim()) {
      extra.ak = form.ak.trim();
    }
    if (form.sk.trim()) {
      extra.sk = form.sk.trim();
    }
    if (form.region.trim()) {
      extra.region = form.region.trim();
    }
    if (form.host.trim()) {
      extra.host = form.host.trim();
    }
    if (Object.keys(extra).length > 0) {
      payload.extra = extra;
    }
  }
  return payload;
}

function doctorTestToast(
  label: string,
  check: OpenVikingDoctorCheck,
): { message: string; tone: AppFeedbackToastTone } {
  const status = check.ok ? "测试通过" : "测试未通过";
  const detail = check.detail?.trim() || check.fix?.trim() || "";
  return {
    message: `${label} ${status}${detail ? `：${detail}` : ""}`,
    tone: check.ok ? "success" : "error",
  };
}

function OpenVikingEmbeddingCard({
  embedding,
  candidates,
  configuredSecrets,
  feedback,
  loading,
  onRefresh,
  requestConfirm,
}: {
  embedding?: OpenVikingEmbeddingResponse;
  candidates: OpenVikingEmbeddingCandidate[];
  configuredSecrets: OpenVikingEmbeddingSecretRef[];
  feedback: DashboardFeedback;
  loading: boolean;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const [form, setForm] = useState<EmbeddingFormState>(EMPTY_EMBEDDING_FORM);
  const [initializedFor, setInitializedFor] = useState<number | null>(null);
  const [probedModels, setProbedModels] = useState<OpenVikingEmbeddingCandidate[] | null>(null);
  const [probeStatus, setProbeStatus] = useState<{ ok: boolean; text: string } | null>(null);

  const applyMutation = useMutation({
    mutationFn: applyEmbeddingConfig,
    onError: (error) => feedback.showError(`保存 Embedding 配置失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("Embedding 配置已保存");
    },
  });
  const testMutation = useMutation({
    mutationFn: testEmbeddingConfig,
    onError: (error) => {
      feedback.showToast(`测试 Embedding 配置失败：${messageFromApiError(error)}`, { tone: "error" });
    },
    onSuccess: (data) => {
      const toast = doctorTestToast(
        "Embedding",
        data.doctor.embedding ?? { ok: false, detail: "无诊断结果", fix: null },
      );
      feedback.showToast(toast.message, { tone: toast.tone });
    },
  });
  const rebuildMutation = useMutation({
    mutationFn: rebuildEmbedding,
    onError: (error) => feedback.showError(`重建向量索引失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("向量索引重建已提交");
    },
  });
  const probeMutation = useMutation({
    mutationFn: (baseUrl: string) => listEmbeddingCandidates(baseUrl),
    onError: (error) => {
      setProbedModels(null);
      setProbeStatus({ ok: false, text: `探测失败：${messageFromApiError(error)}` });
    },
    onSuccess: (data) => {
      const models = data.items.filter((candidate) => candidate.provider === "ollama");
      if (data.ollama && data.ollama.healthy === false) {
        setProbedModels([]);
        setProbeStatus({ ok: false, text: `探测失败：${data.ollama.error ?? "Ollama 不可达"}` });
        return;
      }
      setProbedModels(models);
      setProbeStatus({ ok: true, text: `发现 ${models.length} 个模型` });
    },
  });
  const mutationError =
    mutationErrorMessage(applyMutation.error) ?? mutationErrorMessage(rebuildMutation.error);
  const rebuildProgress = syncProgressView(embedding?.rebuild_progress);

  useEffect(() => {
    if (embedding && initializedFor !== embedding.id) {
      setForm(embeddingFormFromResponse(embedding));
      setInitializedFor(embedding.id);
      setProbedModels(null);
      setProbeStatus(null);
    }
  }, [embedding, initializedFor]);

  const provider = form.provider;
  const isLocal = provider === "local";
  const isOllama = provider === "ollama";
  const isVikingDb = provider === "vikingdb";
  const isCloud = CLOUD_EMBEDDING_PROVIDERS.has(provider);
  const providerUnchanged = embedding?.provider === provider;
  const ollamaModelOptions = candidates.filter((candidate) => candidate.provider === "ollama");
  const ollamaSuggestions = probedModels ?? ollamaModelOptions;
  const normalizedBaseUrl = form.base_url.trim().replace(/\/+$/, "");
  // A saved credential exists for this provider + API base, so leaving the secret
  // blank reuses it server-side — even after switching provider away and back.
  const hasReusableSecret = configuredSecrets.some(
    (ref) => ref.provider === provider && ref.base_url === normalizedBaseUrl,
  );
  const keepSecretHint =
    (providerUnchanged && Boolean(embedding?.api_key_configured)) || hasReusableSecret;
  const apiKeyPlaceholder = keepSecretHint ? "已配置 · 留空复用已保存的密钥" : "sk-…";
  const vikingSecretPlaceholder = (label: string) =>
    keepSecretHint ? "已配置 · 留空复用已保存的密钥" : label;

  function updateForm(patch: Partial<EmbeddingFormState>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function clearProbe() {
    setProbedModels(null);
    setProbeStatus(null);
  }

  function handleBaseUrlChange(value: string) {
    updateForm({ base_url: value });
    // probed models are scoped to the host that was queried; drop them once the URL edits.
    clearProbe();
  }

  function handleProbe() {
    const baseUrl = form.base_url.trim();
    if (!baseUrl) {
      return;
    }
    probeMutation.mutate(baseUrl);
  }

  function handleProviderChange(next: string) {
    const defaults = EMBEDDING_PROVIDER_DEFAULTS[next];
    setForm((current) => ({
      ...current,
      provider: next,
      model:
        defaults?.model ?? (next === embedding?.provider ? embedding?.model ?? "" : ""),
      dimension:
        defaults?.dimension != null
          ? String(defaults.dimension)
          : next === embedding?.provider && embedding?.dimension != null
            ? String(embedding.dimension)
            : "",
    }));
    clearProbe();
  }

  function handleTest() {
    testMutation.mutate(buildEmbeddingApply(form));
  }

  function handleSave() {
    if (!embedding || !form.model.trim()) {
      return;
    }
    requestConfirm({
      confirmLabel: "确认保存",
      message: "确认切换 Embedding 配置？这会清理 OpenViking 索引并重新排队同步任务。",
      onConfirm: () => {
        feedback.showSuccess("Embedding 配置保存已提交");
        applyMutation.mutate(buildEmbeddingApply(form));
      },
      title: "确认切换 Embedding 配置",
      tone: "danger",
    });
  }

  function handleRebuild() {
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
        description="语义索引使用的向量模型；切换会清空索引并触发全量重建。"
        icon={<Database aria-hidden="true" size={16} />}
        title="Embedding 模型"
      />
      {loading ? <p className="empty-note">正在读取 Embedding 配置</p> : null}
      {embedding ? (
        <>
          <div className="ov-config-summary">
            <ConfigStat label="Provider" value={embedding.provider} />
            <ConfigStat label="当前模型" mono value={displayValue(embedding.model)} />
            <ConfigStat label="维度" mono value={displayValue(embedding.dimension)} />
            <ConfigStat label="最大并发" mono value={displayValue(embedding.max_concurrent)} />
            <ConfigStat
              label="API Key"
              mono
              value={embedding.api_key_configured ? (embedding.api_key_masked ?? "已配置") : "未配置"}
            />
            <ConfigStat label="重建状态" value={displayValue(embedding.rebuild_status)} />
          </div>
          {embedding.local_cache ? (
            <p className="settings-openviking-muted">
              本地模型缓存：
              {embedding.local_cache.model_cached ? "已缓存" : "未缓存，首次启动会自动下载"}
              {embedding.local_cache.cache_path ? ` · ${embedding.local_cache.cache_path}` : ""}
            </p>
          ) : null}
          {rebuildProgress.value !== null ? (
            <div className="settings-openviking-progress settings-openviking-progress-block">
              <progress aria-label="Embedding 重建进度" max={100} value={rebuildProgress.value} />
              <small>
                {rebuildProgress.label} · ETA {rebuildProgress.eta}
              </small>
            </div>
          ) : null}

          <div className="settings-openviking-model-form">
            <label className="settings-openviking-field">
              <span>Provider</span>
              <select value={provider} onChange={(event) => handleProviderChange(event.target.value)}>
                {EMBEDDING_PROVIDER_OPTIONS.map((option) => (
                  <option value={option.value} key={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="settings-openviking-field-grid">
              {isLocal ? (
                <>
                  <ReadonlyField label="模型" value={form.model} />
                  <ReadonlyField label="维度" value={form.dimension} />
                  <p className="settings-openviking-muted settings-openviking-field-note">
                    内置 GGUF 模型，无需 Ollama；缓存缺失时首次启动会自动下载。
                  </p>
                </>
              ) : null}

              {isOllama ? (
                <>
                  <TextField
                    label="Base URL"
                    mono
                    value={form.base_url}
                    placeholder="http://127.0.0.1:11434"
                    onChange={handleBaseUrlChange}
                  />
                  <label className="settings-openviking-field">
                    <span>模型</span>
                    <input
                      className="console-mono"
                      list="ov-ollama-model-suggestions"
                      value={form.model}
                      placeholder="bge-m3"
                      onChange={(event) => updateForm({ model: event.target.value })}
                    />
                    <datalist id="ov-ollama-model-suggestions">
                      {ollamaSuggestions.map((candidate) => (
                        <option value={candidate.model} key={`${candidate.source}:${candidate.model}`} />
                      ))}
                    </datalist>
                  </label>
                  <TextField
                    label="维度"
                    value={form.dimension}
                    placeholder="1024"
                    inputMode="numeric"
                    onChange={(value) => updateForm({ dimension: value })}
                  />
                  <TextField
                    label="最大并发"
                    value={form.max_concurrent}
                    placeholder="1"
                    inputMode="numeric"
                    onChange={(value) => updateForm({ max_concurrent: value })}
                  />
                </>
              ) : null}

              {isCloud ? (
                <>
                  <TextField
                    label="API Base"
                    mono
                    value={form.base_url}
                    placeholder="https://api.openai.com/v1"
                    onChange={(value) => updateForm({ base_url: value })}
                  />
                  <TextField
                    label="模型"
                    mono
                    value={form.model}
                    placeholder="text-embedding-3-small"
                    onChange={(value) => updateForm({ model: value })}
                  />
                  <TextField
                    label="维度"
                    value={form.dimension}
                    placeholder="可选"
                    inputMode="numeric"
                    onChange={(value) => updateForm({ dimension: value })}
                  />
                  <SecretField
                    label="API Key"
                    value={form.api_key}
                    placeholder={apiKeyPlaceholder}
                    onChange={(value) => updateForm({ api_key: value })}
                  />
                  <TextField
                    label="最大并发"
                    value={form.max_concurrent}
                    placeholder="1"
                    inputMode="numeric"
                    onChange={(value) => updateForm({ max_concurrent: value })}
                  />
                </>
              ) : null}

              {isVikingDb ? (
                <>
                  <SecretField
                    label="AK"
                    value={form.ak}
                    placeholder={vikingSecretPlaceholder("Access Key")}
                    onChange={(value) => updateForm({ ak: value })}
                  />
                  <SecretField
                    label="SK"
                    value={form.sk}
                    placeholder={vikingSecretPlaceholder("Secret Key")}
                    onChange={(value) => updateForm({ sk: value })}
                  />
                  <TextField
                    label="Region"
                    value={form.region}
                    placeholder="cn-beijing"
                    onChange={(value) => updateForm({ region: value })}
                  />
                  <TextField
                    label="Host"
                    mono
                    value={form.host}
                    placeholder="可选"
                    onChange={(value) => updateForm({ host: value })}
                  />
                  <TextField
                    label="模型"
                    mono
                    value={form.model}
                    placeholder="向量模型名"
                    onChange={(value) => updateForm({ model: value })}
                  />
                  <TextField
                    label="维度"
                    value={form.dimension}
                    placeholder="可选"
                    inputMode="numeric"
                    onChange={(value) => updateForm({ dimension: value })}
                  />
                </>
              ) : null}
            </div>

            {isOllama ? (
              <div className="settings-openviking-probe-row">
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={handleProbe}
                  disabled={probeMutation.isPending || !form.base_url.trim()}
                >
                  {probeMutation.isPending ? "探测中…" : "探测模型"}
                </button>
                {probeStatus ? (
                  <span
                    className="settings-openviking-probe-status"
                    data-ok={probeStatus.ok ? "true" : "false"}
                  >
                    {probeStatus.text}
                  </span>
                ) : (
                  <span className="settings-openviking-probe-status settings-openviking-probe-hint">
                    按当前 Base URL 实时探测该 Ollama 可用模型
                  </span>
                )}
              </div>
            ) : null}

            <div className="settings-openviking-form-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={handleTest}
                disabled={testMutation.isPending || !form.model.trim()}
              >
                {testMutation.isPending ? "测试中…" : "测试"}
              </button>
              <button
                className="button button-danger"
                type="button"
                onClick={handleSave}
                disabled={applyMutation.isPending || !form.model.trim()}
              >
                保存并切换
              </button>
              <button className="button button-secondary" type="button" onClick={handleRebuild}>
                重建向量索引
              </button>
            </div>
          </div>

          <p className="settings-openviking-muted">
            「测试」仅用临时配置运行 OpenViking doctor，不保存、不重启、不清索引；「保存并切换」才会清空索引并重排同步任务。
          </p>
          {mutationError ? <StatusError text={mutationError} /> : null}
        </>
      ) : null}
    </section>
  );
}

interface VLMFormState {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
  temperature: string;
  timeout: string;
  max_retries: string;
}

function vlmFormFromResponse(vlm?: OpenVikingVLMResponse): VLMFormState {
  return {
    enabled: vlm?.enabled ?? false,
    provider: vlm?.provider ?? "",
    base_url: vlm?.base_url ?? "",
    model: vlm?.model ?? "",
    api_key: "",
    temperature: vlm?.temperature != null ? String(vlm.temperature) : "0.0",
    timeout: vlm?.timeout != null ? String(vlm.timeout) : "60.0",
    max_retries: vlm?.max_retries != null ? String(vlm.max_retries) : "3",
  };
}

function buildVLMApply(form: VLMFormState): OpenVikingVLMApplyRequest {
  const payload: OpenVikingVLMApplyRequest = {
    enabled: true,
    provider: form.provider.trim(),
    model: form.model.trim(),
  };
  if (form.base_url.trim()) {
    payload.base_url = form.base_url.trim();
  }
  if (form.api_key.trim()) {
    payload.api_key = form.api_key.trim();
  }
  const temperature = toFloatOrNull(form.temperature);
  if (temperature !== null) {
    payload.temperature = temperature;
  }
  const timeout = toFloatOrNull(form.timeout);
  if (timeout !== null) {
    payload.timeout = timeout;
  }
  const maxRetries = toIntOrNull(form.max_retries);
  if (maxRetries !== null) {
    payload.max_retries = maxRetries;
  }
  return payload;
}

function OpenVikingVLMCard({
  vlm,
  feedback,
  loading,
  onRefresh,
  requestConfirm,
}: {
  vlm?: OpenVikingVLMResponse;
  feedback: DashboardFeedback;
  loading: boolean;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const [form, setForm] = useState<VLMFormState>(() => vlmFormFromResponse());
  const [initialized, setInitialized] = useState(false);

  const applyMutation = useMutation({
    mutationFn: applyVLMConfig,
    onError: (error) => feedback.showError(`保存 VLM 配置失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("VLM 配置已保存");
    },
  });
  const disableMutation = useMutation({
    mutationFn: disableVLMConfig,
    onError: (error) => feedback.showError(`禁用 VLM 失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("VLM 已禁用");
    },
  });
  const testMutation = useMutation({
    mutationFn: testVLMConfig,
    onError: (error) => {
      feedback.showToast(`测试 VLM 配置失败：${messageFromApiError(error)}`, { tone: "error" });
    },
    onSuccess: (data) => {
      const toast = doctorTestToast(
        "VLM",
        data.doctor.vlm ?? { ok: false, detail: "无诊断结果", fix: null },
      );
      feedback.showToast(toast.message, { tone: toast.tone });
    },
  });
  const mutationError =
    mutationErrorMessage(applyMutation.error) ?? mutationErrorMessage(disableMutation.error);

  useEffect(() => {
    if (vlm && !initialized) {
      setForm(vlmFormFromResponse(vlm));
      setInitialized(true);
    }
  }, [vlm, initialized]);

  const apiKeyPlaceholder =
    vlm?.enabled && vlm.provider === form.provider.trim() && vlm.api_key_configured
      ? `${vlm.api_key_masked ?? "已配置"} · 留空保持不变`
      : "可选";

  function updateForm(patch: Partial<VLMFormState>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function handleTest() {
    testMutation.mutate(buildVLMApply(form));
  }

  const currentEnabled = vlm?.enabled ?? false;
  const busy = applyMutation.isPending || disableMutation.isPending;

  // 开关名副其实：拨到「开」+保存=配置并启用；拨到「关」+保存=调 disable 接口禁用。
  function handleApply() {
    if (form.enabled) {
      if (!form.provider.trim() || !form.model.trim()) {
        feedback.showError("请填写 VLM provider 和模型");
        return;
      }
      requestConfirm({
        confirmLabel: "确认启用",
        message: "确认更新并启用 VLM？这会重启 OpenViking，但不会清理向量索引。",
        onConfirm: () => {
          feedback.showSuccess("VLM 配置保存已提交");
          applyMutation.mutate(buildVLMApply(form));
        },
        title: "确认启用 VLM",
        tone: "warning",
      });
      return;
    }
    requestConfirm({
      confirmLabel: "确认禁用",
      message: "确认禁用 VLM？这会重启 OpenViking 并移除 ov.conf 中的 vlm 段。",
      onConfirm: () => {
        feedback.showSuccess("VLM 禁用已提交");
        disableMutation.mutate();
      },
      title: "确认禁用 VLM",
      tone: "warning",
    });
  }

  return (
    <section className="surface openviking-card openviking-card-vlm" aria-label="OpenViking VLM">
      <OpenVikingCardHeader
        description="可选的视觉语言模型；变更只重启 OpenViking，不清向量索引。"
        icon={<Eye aria-hidden="true" size={16} />}
        title="VLM 模型"
      />
      {loading ? <p className="empty-note">正在读取 VLM 配置</p> : null}
      {!loading ? (
        <>
          <div className="ov-config-summary">
            <ConfigStat
              label="状态"
              tone={currentEnabled ? "ok" : "idle"}
              value={currentEnabled ? "已启用" : "未配置"}
            />
            <ConfigStat label="Provider" value={vlm?.provider ?? EMPTY_VALUE} />
            <ConfigStat label="模型" mono value={vlm?.model ?? EMPTY_VALUE} />
            <ConfigStat
              label="API Key"
              mono
              value={vlm?.api_key_configured ? (vlm.api_key_masked ?? "已配置") : "未配置"}
            />
          </div>

          <div className="settings-openviking-model-form">
            <div className="console-toggle-row">
              <div className="console-toggle-text">
                <strong>启用 VLM</strong>
                <small>关闭后保存即移除 VLM 配置；可选能力，关闭不算故障</small>
              </div>
              <SwitchControl
                checked={form.enabled}
                label="启用 VLM"
                text={form.enabled ? "开启" : "关闭"}
                onChange={(checked) => updateForm({ enabled: checked })}
              />
            </div>
            <div className="settings-openviking-field-grid" data-disabled={form.enabled ? undefined : "true"}>
              <label className="settings-openviking-field">
                <span>Provider</span>
                <input
                  list="ov-vlm-provider-suggestions"
                  value={form.provider}
                  placeholder="volcengine / litellm / …"
                  onChange={(event) => updateForm({ provider: event.target.value })}
                />
                <datalist id="ov-vlm-provider-suggestions">
                  {VLM_PROVIDER_SUGGESTIONS.map((suggestion) => (
                    <option value={suggestion} key={suggestion} />
                  ))}
                </datalist>
              </label>
              <TextField
                label="Base URL"
                mono
                value={form.base_url}
                placeholder="可选"
                onChange={(value) => updateForm({ base_url: value })}
              />
              <TextField
                label="模型"
                mono
                value={form.model}
                placeholder="模型名"
                onChange={(value) => updateForm({ model: value })}
              />
              <SecretField
                label="API Key"
                value={form.api_key}
                placeholder={apiKeyPlaceholder}
                onChange={(value) => updateForm({ api_key: value })}
              />
              <TextField
                label="Temperature"
                value={form.temperature}
                placeholder="0.0"
                inputMode="decimal"
                onChange={(value) => updateForm({ temperature: value })}
              />
              <TextField
                label="Timeout"
                value={form.timeout}
                placeholder="60.0"
                inputMode="decimal"
                onChange={(value) => updateForm({ timeout: value })}
              />
              <TextField
                label="Max retries"
                value={form.max_retries}
                placeholder="3"
                inputMode="numeric"
                onChange={(value) => updateForm({ max_retries: value })}
              />
            </div>

            <div className="settings-openviking-form-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={handleTest}
                disabled={
                  testMutation.isPending || !form.enabled || !form.provider.trim() || !form.model.trim()
                }
              >
                {testMutation.isPending ? "测试中…" : "测试"}
              </button>
              <button
                className={form.enabled ? "button button-primary" : "button button-danger"}
                type="button"
                onClick={handleApply}
                disabled={busy || (!form.enabled && !currentEnabled)}
              >
                {form.enabled ? "保存并启用" : "禁用 VLM"}
              </button>
            </div>
          </div>

          <p className="settings-openviking-muted">
            拨动开关后点「保存」即生效：启用会按当前配置写入，关闭会移除 VLM 段——两者都会重启 OpenViking，但不触发索引重建。
          </p>
          {mutationError ? <StatusError text={mutationError} /> : null}
        </>
      ) : null}
    </section>
  );
}

function ConfigStat({
  label,
  mono,
  tone,
  value,
}: {
  label: string;
  mono?: boolean;
  tone?: "ok" | "idle";
  value: string;
}) {
  return (
    <div className="console-stat" data-tone={tone}>
      <span className="console-stat-label">{label}</span>
      <strong className={mono ? "console-mono" : undefined}>{value}</strong>
    </div>
  );
}

function ReadonlyField({ label, value }: { label: string; value: string }) {
  return (
    <label className="settings-openviking-field">
      <span>{label}</span>
      <input value={value} className="console-mono" readOnly tabIndex={-1} aria-readonly="true" />
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  inputMode,
  mono,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  inputMode?: "numeric" | "decimal" | "text";
  mono?: boolean;
}) {
  return (
    <label className="settings-openviking-field">
      <span>{label}</span>
      <input
        className={mono ? "console-mono" : undefined}
        value={value}
        placeholder={placeholder}
        inputMode={inputMode}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SecretField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="settings-openviking-field">
      <span>{label}</span>
      <input
        type="password"
        autoComplete="new-password"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function DoctorResultLine({ label, check }: { label: string; check: OpenVikingDoctorCheck }) {
  return (
    <div className="settings-openviking-doctor-line" data-ok={check.ok ? "true" : "false"}>
      <span className="settings-openviking-doctor-icon" aria-hidden="true">
        {check.ok ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
      </span>
      <div>
        <strong>{label}</strong>
        <p>{check.detail ?? (check.ok ? "正常" : "未通过")}</p>
        {check.fix ? <small>修复建议：{check.fix}</small> : null}
      </div>
    </div>
  );
}

function OpenVikingDoctorPanel({
  doctor,
  ollamaConfigured,
  vlmEnabled,
}: {
  doctor: OpenVikingDoctorReport;
  ollamaConfigured: boolean;
  vlmEnabled: boolean;
}) {
  const lines: Array<{ label: string; check: OpenVikingDoctorCheck }> = [];
  if (doctor.embedding) {
    lines.push({ label: "Embedding", check: doctor.embedding });
  }
  if (doctor.vlm) {
    const check = vlmEnabled
      ? doctor.vlm
      : { ok: true, detail: doctor.vlm.detail ?? "未配置（可选）", fix: null };
    lines.push({ label: "VLM", check });
  }
  if (doctor.ollama && ollamaConfigured) {
    lines.push({ label: "Ollama", check: doctor.ollama });
  }
  if (lines.length === 0) {
    return null;
  }
  return (
    <div className="settings-openviking-doctor">
      <div className="settings-openviking-doctor-head">
        <Stethoscope aria-hidden="true" size={14} />
        <span>OpenViking doctor</span>
      </div>
      {lines.map((line) => (
        <DoctorResultLine key={line.label} label={line.label} check={line.check} />
      ))}
    </div>
  );
}

function toIntOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null;
}

function toFloatOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function toPositiveInt(value: string, fallback: number): number {
  const parsed = toIntOrNull(value);
  return parsed && parsed > 0 ? parsed : fallback;
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
  const [statusFilter, setStatusFilter] = useState("");
  const [jobPage, setJobPage] = useState(1);
  const [jobPageSize, setJobPageSize] = useState(JOB_PAGE_SIZE);

  const shouldPoll =
    !statusFilter || statusFilter === "pending" || statusFilter === "running" || statusFilter === "failed";

  const jobsQuery = useQuery({
    queryKey: ["admin-openviking-sync-jobs", statusFilter, jobPage, jobPageSize],
    queryFn: () =>
      listOpenVikingSyncJobs({
        status: statusFilter || undefined,
        page: jobPage,
        limit: jobPageSize,
      }),
    refetchInterval: shouldPoll ? 5000 : false,
  });

  useEffect(() => {
    setJobPage(1);
  }, [statusFilter, jobPageSize]);

  const counts = summaryQuery.data?.counts ?? {};
  const jobs = jobsQuery.data?.items ?? [];
  // 列表条数与页数都以「当前过滤后的查询结果」为准，避免和独立轮询的汇总计数节奏不一致导致页数抖动。
  const total = jobsQuery.data?.total ?? 0;
  const currentPage = jobsQuery.data?.page ?? jobPage;
  const totalPages = Math.max(1, Math.ceil(total / jobPageSize));
  const hasNext = currentPage < totalPages;
  const hasPrevious = currentPage > 1;
  const [jumpValue, setJumpValue] = useState(String(jobPage));

  useEffect(() => {
    setJumpValue(String(jobPage));
  }, [jobPage]);

  function handleRetry(jobId: string) {
    requestConfirm({
      confirmLabel: "确认重试",
      message: `确认重试同步任务 ${jobId}？`,
      onConfirm: () => {
        feedback.showSuccess("重试任务已提交");
        retryMutation.mutate(jobId);
      },
      title: "确认重试同步任务",
    });
  }

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
        <StatusPill label="等待中" value={String(counts.pending ?? 0)} onClick={() => setStatusFilter(statusFilter === "pending" ? "" : "pending")} selected={statusFilter === "pending"} />
        <StatusPill label="运行中" value={String(counts.running ?? 0)} onClick={() => setStatusFilter(statusFilter === "running" ? "" : "running")} selected={statusFilter === "running"} />
        <StatusPill
          label="失败"
          value={String(counts.failed ?? 0)}
          tone={counts.failed ? "error" : "info"}
          onClick={() => setStatusFilter(statusFilter === "failed" ? "" : "failed")}
          selected={statusFilter === "failed"}
        />
        <StatusPill
          label="已停止重试"
          value={String(counts.cancelled ?? 0)}
          tone={counts.cancelled ? "error" : "info"}
          onClick={() => setStatusFilter(statusFilter === "cancelled" ? "" : "cancelled")}
          selected={statusFilter === "cancelled"}
        />
        <StatusPill label="已索引" value={String(counts.indexed ?? 0)} tone="success" onClick={() => setStatusFilter(statusFilter === "indexed" ? "" : "indexed")} selected={statusFilter === "indexed"} />
      </div>
      <ul className="data-list settings-config-list console-config-list settings-openviking-job-list">
        {jobs.map((job) => (
          <SyncJobItem job={job} key={job.id} onRetry={() => handleRetry(job.id)} />
        ))}
      </ul>
      {jobs.length === 0 && !jobsQuery.isLoading ? (
        <p className="empty-note">暂无同步任务</p>
      ) : null}
      {jobsQuery.isLoading ? (
        <p className="settings-openviking-muted">正在读取同步任务...</p>
      ) : null}
      <div className="settings-openviking-pagination" aria-label="同步任务分页">
        <div className="settings-openviking-pagination-summary">
          <span>共 {total} 条 · 第 {currentPage} / {totalPages} 页</span>
          <label>
            <span>每页</span>
            <select
              aria-label="同步任务每页条数"
              value={jobPageSize}
              onChange={(event) => setJobPageSize(Number(event.target.value))}
            >
              <option value={5}>5 条</option>
              <option value={10}>10 条</option>
              <option value={20}>20 条</option>
              <option value={50}>50 条</option>
            </select>
          </label>
        </div>
        <div className="settings-openviking-pagination-actions">
          <button
            aria-label="上一页同步任务"
            className="button button-secondary"
            type="button"
            onClick={() => setJobPage((prev) => Math.max(1, prev - 1))}
            disabled={!hasPrevious || jobsQuery.isLoading}
          >
            上一页
          </button>
          <form className="settings-openviking-page-jump" onSubmit={(event) => { event.preventDefault(); const num = Number(jumpValue); if (num >= 1 && num <= totalPages) { setJobPage(num); setJumpValue(""); } }}>
            <label>
              <span>跳至</span>
              <input
                aria-label="同步任务页码"
                max={totalPages}
                min={1}
                type="number"
                value={jumpValue}
                onChange={(event) => setJumpValue(event.target.value)}
              />
            </label>
            <button
              aria-label="跳转同步任务页"
              className="button button-secondary"
              disabled={jobsQuery.isLoading}
              type="submit"
            >
              跳转
            </button>
          </form>
          <button
            aria-label="下一页同步任务"
            className="button button-secondary"
            type="button"
            onClick={() => setJobPage((prev) => prev + 1)}
            disabled={!hasNext || jobsQuery.isLoading}
          >
            下一页
          </button>
        </div>
      </div>
      {mutationError ? <StatusError text={mutationError} /> : null}
    </section>
  );
}

function SyncJobItem({ job, onRetry }: { job: OpenVikingSyncJob; onRetry: () => void }) {
  const progress = syncProgressView(job.progress);
  const hasProgress = progress.value !== null;
  const [detailsOpen, setDetailsOpen] = useState(false);
  const statusLabel = SYNC_STATUS_LABELS[job.status] ?? job.status;
  const showRetry = job.status === "failed" || job.status === "cancelled";
  const metaLine = jobMetaLine(job);
  const errorHint = syncJobErrorHint(job);
  const title = syncJobTitle(job);
  const displayName = syncJobDisplayName(job);
  const suggestion = syncJobSuggestion(job, errorHint);
  const statusDescription = syncJobStatusDescription(job);
  return (
    <li className="settings-openviking-job-row" data-status={job.status}>
      <div className="settings-openviking-job-header">
        <div className="settings-openviking-row-main">
          <span className="settings-openviking-job-kind">{title}</span>
          <strong>{displayName}</strong>
          {statusDescription ? <span>{statusDescription}</span> : null}
          <div className="settings-openviking-job-context">
            {job.feature_slug ? <small>所属特性 {job.feature_slug}</small> : null}
            {job.updated_at ? <small>更新于 {formatDisplayDateTime(job.updated_at)}</small> : null}
            {metaLine ? <small>{metaLine}</small> : null}
          </div>
        </div>
        <div className="settings-openviking-job-actions">
          {showRetry ? (
            <button
              aria-label={`重试 ${job.id}`}
              className="button button-secondary settings-openviking-job-detail-button"
              type="button"
              onClick={onRetry}
            >
              重试
            </button>
          ) : null}
          <button
            className="button button-secondary settings-openviking-job-detail-button"
            type="button"
            onClick={() => setDetailsOpen((current) => !current)}
          >
            {detailsOpen ? "收起详情" : "详情"}
          </button>
          <Badge text={statusLabel} outcome={statusOutcome(job.status)} />
        </div>
      </div>
      {hasProgress ? (
        <div className="settings-openviking-progress">
          <progress
            aria-label={`${job.id} 同步进度`}
            max={100}
            value={progress.value!}
          />
          <small>进度 {progress.label}</small>
          <small>预计剩余 {progress.eta}</small>
        </div>
      ) : null}
      {suggestion ? (
        <div className="console-status-line ov-advice" data-tone="warning">
          <AlertTriangle aria-hidden="true" size={15} />
          <span>{suggestion}</span>
        </div>
      ) : null}
      {detailsOpen ? <SyncJobDetails job={job} /> : null}
    </li>
  );
}

function SyncJobDetails({ job }: { job: OpenVikingSyncJob }) {
  const details = [
    ["任务 ID", job.id],
    ["来源类型", job.source_type],
    ["来源 ID", job.source_id],
    ["同步动作", syncJobOperationLabel(job)],
    ["Viking URI", job.viking_uri],
    ["重试次数", String(job.attempts)],
    ["下次重试", job.next_retry_at ? formatDisplayDateTime(job.next_retry_at) : null],
    ["最近同步", job.last_synced_at ? formatDisplayDateTime(job.last_synced_at) : null],
    ["最近索引", job.last_indexed_at ? formatDisplayDateTime(job.last_indexed_at) : null],
    ["原始错误", job.error],
  ].filter(([, value]) => Boolean(value));
  return (
    <dl className="settings-openviking-job-details">
      {details.map(([label, value]) => (
        <div className="settings-openviking-job-detail" key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function OpenVikingEventStream({
  events,
  eventTypeOptions,
  feedback,
  hasNext,
  hasPrevious,
  isLoading,
  outcome,
  eventType,
  eventView,
  onRefresh,
  onOutcomeChange,
  onEventTypeChange,
  onEventViewChange,
  onNextPage,
  onPageJump,
  onPageSizeChange,
  onPreviousPage,
  pageNumber,
  pageSize,
  pageSizeOptions,
  requestConfirm,
  total,
  totalPages,
}: {
  events: OpenVikingDashboardEvent[];
  eventTypeOptions: string[];
  feedback: DashboardFeedback;
  hasNext: boolean;
  hasPrevious: boolean;
  isLoading: boolean;
  outcome: string;
  eventType: string;
  eventView: EventView;
  onRefresh: () => void;
  onOutcomeChange: (value: string) => void;
  onEventTypeChange: (value: string) => void;
  onEventViewChange: (value: EventView) => void;
  onNextPage: () => void;
  onPageJump: (value: number) => void;
  onPageSizeChange: (value: number) => void;
  onPreviousPage: () => void;
  pageNumber: number;
  pageSize: number;
  pageSizeOptions: number[];
  requestConfirm: DashboardConfirm;
  total: number;
  totalPages: number;
}) {
  const [jumpValue, setJumpValue] = useState(String(pageNumber));
  const eventTypes = Array.from(
    new Set([...eventTypeOptions, eventType].filter((value): value is string => Boolean(value))),
  ).sort();

  useEffect(() => {
    setJumpValue(String(pageNumber));
  }, [pageNumber]);

  function handleJumpSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextPage = Number.parseInt(jumpValue, 10);
    if (Number.isFinite(nextPage)) {
      onPageJump(nextPage);
    }
  }

  return (
    <section className="surface openviking-card openviking-card-events" aria-label="OpenViking 事件流">
      <OpenVikingCardHeader
        description="同步、调优、重启和错误事件的时间线。"
        icon={<Activity aria-hidden="true" size={16} />}
        title="事件流"
      />
      <div className="settings-openviking-filter-row">
        <label className="settings-openviking-field">
          <span>范围</span>
          <select
            aria-label="事件范围"
            value={eventView}
            onChange={(event) => onEventViewChange(event.target.value as EventView)}
          >
            <option value="important">重点事件</option>
            <option value="all">全部事件</option>
          </select>
        </label>
        <label className="settings-openviking-field">
          <span>结果</span>
          <select
            aria-label="事件结果过滤"
            value={outcome}
            onChange={(event) => onOutcomeChange(event.target.value)}
          >
            <option value="">全部</option>
            <option value="info">info</option>
            <option value="success">success</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
        <label className="settings-openviking-field">
          <span>类型</span>
          <select
            aria-label="事件类型过滤"
            value={eventType}
            onChange={(event) => onEventTypeChange(event.target.value)}
          >
            <option value="">全部</option>
            {eventTypes.map((type) => (
              <option value={type} key={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ul className="data-list settings-config-list console-config-list settings-openviking-event-list">
        {events.map((event) => (
          <EventItem
            event={event}
            feedback={feedback}
            key={event.id}
            onRefresh={onRefresh}
            requestConfirm={requestConfirm}
          />
        ))}
      </ul>
      {events.length === 0 && !isLoading ? <p className="empty-note">暂无 OpenViking 事件</p> : null}
      {isLoading ? <p className="settings-openviking-muted">正在读取事件页...</p> : null}
      <div className="settings-openviking-pagination" aria-label="事件分页">
        <div className="settings-openviking-pagination-summary">
          <span>共 {total} 条 · 第 {pageNumber} / {totalPages} 页</span>
          <label>
            <span>每页</span>
            <select
              aria-label="事件每页条数"
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
            >
              {pageSizeOptions.map((option) => (
                <option value={option} key={option}>
                  {option} 条
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="settings-openviking-pagination-actions">
          <button
            aria-label="上一页事件"
            className="button button-secondary"
            type="button"
            onClick={onPreviousPage}
            disabled={!hasPrevious || isLoading}
          >
            上一页
          </button>
          <form className="settings-openviking-page-jump" onSubmit={handleJumpSubmit}>
            <label>
              <span>跳至</span>
              <input
                aria-label="事件页码"
                max={totalPages}
                min={1}
                type="number"
                value={jumpValue}
                onChange={(event) => setJumpValue(event.target.value)}
              />
            </label>
            <button
              aria-label="跳转事件页"
              className="button button-secondary"
              disabled={isLoading}
              type="submit"
            >
              跳转
            </button>
          </form>
          <button
            aria-label="下一页事件"
            className="button button-secondary"
            type="button"
            onClick={onNextPage}
            disabled={!hasNext || isLoading}
          >
            下一页
          </button>
        </div>
      </div>
      {pageNumber > 1 ? (
        <p className="settings-openviking-paused-note">
          正在查看历史事件页，实时刷新暂停；回到第 1 页后恢复刷新。
        </p>
      ) : null}
    </section>
  );
}

function EventItem({
  event,
  feedback,
  onRefresh,
  requestConfirm,
}: {
  event: OpenVikingDashboardEvent;
  feedback: DashboardFeedback;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  const retryMutation = useMutation({
    mutationFn: retrySyncJob,
    onError: (error) => feedback.showError(`重试任务失败：${messageFromApiError(error)}`),
    onSuccess: () => {
      onRefresh();
      feedback.showSuccess("重试任务已提交");
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
  const remediation = eventRemediation(event);
  const [detailsOpen, setDetailsOpen] = useState(false);

  function handleRemediationAction() {
    if (!remediation?.action) {
      return;
    }
    if (remediation.action === "retry_sync_job") {
      const syncJobId = event.sync_job_id;
      if (!syncJobId) {
        return;
      }
      requestConfirm({
        confirmLabel: "确认重试",
        message: `确认重新入队同步任务 ${syncJobId}？`,
        onConfirm: () => {
          retryMutation.mutate(syncJobId);
        },
        title: "确认重试同步任务",
      });
      return;
    }
    if (remediation.action === "resync") {
      requestConfirm({
        confirmLabel: "确认同步",
        message: "确认立即触发 OpenViking 全量重新同步？",
        onConfirm: () => {
          resyncMutation.mutate({});
        },
        title: "确认立即重新同步",
        tone: "warning",
      });
      return;
    }
    requestConfirm({
      confirmLabel: "确认重建",
      message: "确认重新排队并重建 OpenViking 索引？",
      onConfirm: () => {
        rebuildMutation.mutate();
      },
      title: "确认重试重建",
      tone: "danger",
    });
  }

  return (
    <li className="settings-openviking-row" data-event-type={event.event_type} data-outcome={event.outcome}>
      <div className="settings-openviking-event-main">
        <div className="settings-openviking-event-title">
          <span aria-hidden="true" className="ov-event-dot" data-outcome={event.outcome} />
          <strong>{EVENT_LABELS[event.event_type] ?? event.event_type}</strong>
          <time className="console-mono" dateTime={event.created_at ?? undefined}>
            {formatDateTime(event.created_at)}
          </time>
        </div>
        <span className="settings-openviking-event-description">{describeEvent(event)}</span>
        {remediation ? (
          <div className="console-status-line ov-advice" data-tone="muted">
            <span>建议：{remediation.hint}</span>
            {remediation.action ? (
              <button
                className="button button-secondary ov-advice-action"
                type="button"
                onClick={handleRemediationAction}
              >
                {remediation.label}
              </button>
            ) : null}
          </div>
        ) : null}
        {detailsOpen ? <EventDetails event={event} /> : null}
      </div>
      <button
        aria-expanded={detailsOpen}
        className="button button-secondary settings-openviking-event-detail-button"
        type="button"
        onClick={() => setDetailsOpen((current) => !current)}
      >
        {detailsOpen ? "收起详情" : "详情"}
      </button>
      <Badge text={OUTCOME_LABELS[event.outcome]} outcome={event.outcome} />
    </li>
  );
}

function EventDetails({ event }: { event: OpenVikingDashboardEvent }) {
  const rows = [
    ["事件 ID", String(event.id)],
    ["事件类型", event.event_type],
    ["结果", OUTCOME_LABELS[event.outcome]],
    ["来源", event.source_type ?? EMPTY_VALUE],
    ["来源 ID", event.source_id ?? EMPTY_VALUE],
    ["同步任务", event.sync_job_id ?? EMPTY_VALUE],
    ["触发人", event.triggered_by ?? EMPTY_VALUE],
    ["创建时间", event.created_at ?? EMPTY_VALUE],
  ];
  const payloadText = eventPayloadText(event.payload);
  return (
    <div className="settings-openviking-event-details">
      <dl>
        {rows.map(([label, value]) => (
          <div className="settings-openviking-event-detail-pair" key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {payloadText ? (
        <div className="settings-openviking-event-payload">
          <span>payload</span>
          <pre>{payloadText}</pre>
        </div>
      ) : null}
    </div>
  );
}

function OpenVikingTuningCard({
  feedback,
  tuning,
  preset,
  onRefresh,
  requestConfirm,
}: {
  feedback: DashboardFeedback;
  tuning?: OpenVikingTuningResponse;
  preset: string;
  onRefresh: () => void;
  requestConfirm: DashboardConfirm;
}) {
  // Ollama 已不是默认 embedding 服务，调优页不再展示 ollama_recommend 组与 Ollama snippet。
  const rows = useMemo(
    () => flattenTuningRows(tuning).filter((row) => row.scope !== "ollama_recommend"),
    [tuning],
  );
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
  const mutationError =
    mutationErrorMessage(applyMutation.error) ?? mutationErrorMessage(presetMutation.error);
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
      feedback.showToast("参数值没有变化，无需应用");
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
        <strong className="console-mono">{row.key}</strong>
        <span>{description.description}</span>
        <small>{description.impact}</small>
      </div>
      <input
        aria-label={`自定义值 ${key}`}
        className="console-mono"
        value={draftValue}
        onChange={(event) => onDraftChange(event.target.value)}
      />
      <span className="tuning-recommended">
        推荐 <span className="console-mono">{displayValue(row.recommended)}</span>
      </span>
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
  if (status === "failed" || status === "cancelled") {
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

function indexingPhaseLabel(phase: NonNullable<OpenVikingStatusResponse["indexing"]>["phase"]) {
  const labels: Record<typeof phase, string> = {
    blocked: "需要处理",
    degraded: "已降级",
    embedding: "生成向量",
    idle: "空闲",
    indexed: "已完成",
    syncing: "提交同步",
  };
  return labels[phase] ?? phase;
}

function indexingPhaseTone(
  phase: NonNullable<OpenVikingStatusResponse["indexing"]>["phase"],
): "info" | "success" | "warning" | "error" {
  if (phase === "indexed") {
    return "success";
  }
  if (phase === "blocked" || phase === "degraded") {
    return "error";
  }
  if (phase === "embedding" || phase === "syncing") {
    return "warning";
  }
  return "info";
}

function formatNextRetryAt(iso: string): string {
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    const now = new Date();
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const time = `${hours}:${minutes}`;
    const isSameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();
    return isSameDay ? time : `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${time}`;
  } catch {
    return iso;
  }
}

function formatDisplayDateTime(iso: string): string {
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${month}-${day} ${hours}:${minutes}`;
  } catch {
    return iso;
  }
}

function syncJobSourceLabel(job: OpenVikingSyncJob): string {
  return SYNC_SOURCE_LABELS[job.source_type] ?? job.source_type;
}

function syncJobOperation(job: OpenVikingSyncJob): "delete" | "upsert" {
  const progress = recordFromUnknown(job.progress);
  return progress?.op === "delete" ? "delete" : "upsert";
}

function syncJobOperationLabel(job: OpenVikingSyncJob): string {
  return syncJobOperation(job) === "delete" ? "删除索引" : "同步索引";
}

function syncJobTitle(job: OpenVikingSyncJob): string {
  return `${syncJobOperation(job) === "delete" ? "删除" : "同步"} ${syncJobSourceLabel(job)}`;
}

function syncJobDisplayName(job: OpenVikingSyncJob): string {
  if (job.display_name) {
    return job.display_name;
  }
  if (job.viking_uri) {
    const lastSegment = job.viking_uri.split("/").filter(Boolean).at(-1);
    if (lastSegment) {
      return decodeURIComponent(lastSegment);
    }
  }
  return `${syncJobSourceLabel(job)} ${job.source_id}`;
}

function syncJobStatusDescription(job: OpenVikingSyncJob): string | null {
  if (job.status === "pending") {
    return "排队等待写入语义索引";
  }
  if (job.status === "running") {
    return "正在写入 OpenViking 语义索引";
  }
  if (job.status === "indexed") {
    return null;
  }
  if (job.status === "failed") {
    return "已失败，等待处理或下一次自动重试";
  }
  if (job.status === "cancelled") {
    return "连续失败后已停止自动重试";
  }
  return job.status;
}

function jobMetaLine(job: OpenVikingSyncJob): string | null {
  if (job.status === "cancelled") {
    return "已停止自动重试";
  }
  if (job.status === "failed") {
    const parts: string[] = [];
    if (job.attempts > 0) {
      parts.push(`已重试 ${job.attempts} 次`);
    }
    if (job.next_retry_at) {
      parts.push(`下次约 ${formatNextRetryAt(job.next_retry_at)} 自动重试`);
    }
    return parts.length > 0 ? parts.join(" · ") : null;
  }
  return null;
}

function syncJobSuggestion(job: OpenVikingSyncJob, errorHint: string | null): string | null {
  if (job.status === "failed") {
    return `建议：检查失败原因；${errorHint ?? job.error ?? "确认 OpenViking、Ollama 和资源正文是否正常。"}`;
  }
  if (job.status === "cancelled") {
    return `建议：先确认依赖恢复后手动重试；${errorHint ?? job.error ?? "该任务已停止自动重试。"}`;
  }
  return null;
}

function syncJobErrorHint(job: OpenVikingSyncJob): string | null {
  if (job.status === "cancelled") {
    return "已连续失败 5 次自动停止。请检查 OpenViking 服务是否在线、Embedding 配置是否正确后手动重试。";
  }
  if (!job.error) {
    return null;
  }
  const lower = job.error.toLowerCase();
  if (lower.includes("connection refused") || lower.includes("connect") || lower.includes("unreachable")) {
    return "无法连接 OpenViking 服务，请检查服务是否在线（原始错误见详情）。";
  }
  if (lower.includes("embedding") || lower.includes("dimension")) {
    return "Embedding 模型异常，请检查 Ollama 服务和模型配置（原始错误见详情）。";
  }
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "同步超时，请检查 OpenViking 负载和 Ollama 并发设置（原始错误见详情）。";
  }
  if (lower.includes("auth") || lower.includes("unauthorized") || lower.includes("401") || lower.includes("403")) {
    return "凭据或权限错误，请检查 OpenViking 鉴权配置（原始错误见详情）。";
  }
  return null;
}

type EventRemediation = {
  action?: "rebuild_index" | "resync" | "retry_sync_job";
  hint: string;
  label?: string;
};

function describeEvent(event: OpenVikingDashboardEvent) {
  const payload = recordFromUnknown(event.payload);
  const error = eventErrorText(event, payload);
  const name = eventReadableName(event, payload);
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
  if (event.event_type === "repo_synced") {
    return `仓库 ${name} 已同步`;
  }
  if (event.event_type === "repo_refresh_summary") {
    const reason = stringFromUnknown(payload?.reason) ?? "refresh";
    const summary = `扫描 ${displayNumber(payload?.scanned)} · 成功 ${displayNumber(
      payload?.succeeded,
    )} · 失败 ${displayNumber(payload?.failed)}`;
    return `${reason}：${summary}`;
  }
  if (event.event_type === "sync_job_failed") {
    const attempts = numberFromUnknown(payload?.attempts);
    const retryState = event.outcome === "error" ? "已放弃" : "将重试";
    const suffix = attempts === null ? `（${retryState}）` : `（第 ${attempts} 次，${retryState}）`;
    const body = `${name}索引失败${suffix}`;
    return error ? `${error}；${body}` : body;
  }
  if (event.event_type === "openviking_breaker_tripped") {
    const statusCode =
      stringFromUnknown(payload?.status_code) ??
      numberFromUnknown(payload?.status_code)?.toString() ??
      stringFromUnknown(payload?.status) ??
      numberFromUnknown(payload?.status)?.toString();
    if (statusCode && error) {
      return `OpenViking 返回 ${statusCode}：${error}`;
    }
    return error ? `OpenViking 熔断：${error}` : "OpenViking 熔断已触发";
  }
  if (event.event_type === "openviking_health_failed") {
    const pid = stringFromUnknown(payload?.pid);
    const port = stringFromUnknown(payload?.port);
    const target = [pid ? `pid ${pid}` : null, port ? `端口 ${port}` : null]
      .filter(Boolean)
      .join(" · ");
    const suffix = target ? `；${target}` : "";
    return error ? `${error}${suffix}` : `OpenViking 健康检查失败${suffix}`;
  }
  if (event.event_type === "openviking_restart_detected") {
    const oldPid = stringFromUnknown(payload?.old_pid);
    const newPid = stringFromUnknown(payload?.new_pid) ?? stringFromUnknown(payload?.pid);
    const pidPart = oldPid && newPid ? `pid ${oldPid}→${newPid}` : newPid ? `pid ${newPid}` : "进程重启";
    return error ? `${error}；${pidPart}` : `OpenViking ${pidPart}`;
  }
  if (event.event_type === "scheduled_refresh_summary") {
    const summary = `扫描 ${displayNumber(payload?.scanned)} · 入队 ${displayNumber(
      payload?.enqueued,
    )} · 跳过 ${displayNumber(payload?.skipped)}`;
    return error ? `${error}；${summary}` : summary;
  }
  if (event.event_type === "manual_rebuild_index" && error) {
    return `${error}；重建索引未完成`;
  }
  if (event.event_type === "sync_job_enqueued") {
    return `${name} 已加入同步队列`;
  }
  if (event.event_type === "manual_retry") {
    return `${name} 已手动重试`;
  }
  if (event.event_type === "manual_retry_failed") {
    return error ? `${error}；失败任务重试未完成` : "失败任务已重新入队";
  }
  if (event.event_type === "manual_resync") {
    return error ? `${error}；重新同步未完成` : "重新同步已触发";
  }
  if (error) {
    const summary = payloadSummary(payload);
    return summary ? `${error}；${summary}` : error;
  }
  if (payload?.count !== undefined) {
    return `${event.source_type ?? "system"} · count=${String(payload.count)}`;
  }
  if (payload?.job_id !== undefined) {
    return `${event.source_type ?? "system"} · job=${String(payload.job_id)}`;
  }
  if (name) {
    return `${event.source_type ?? "system"} · ${name}`;
  }
  return event.source_type ?? "system";
}

function eventRemediation(event: OpenVikingDashboardEvent): EventRemediation | null {
  if (event.outcome !== "warning" && event.outcome !== "error") {
    return null;
  }
  if (event.event_type === "sync_job_failed") {
    return {
      action: event.sync_job_id ? "retry_sync_job" : undefined,
      hint: "重新入队该同步任务；如果连续失败，请检查资源正文和 OpenViking 日志。",
      label: event.sync_job_id ? "重试该任务" : undefined,
    };
  }
  if (event.event_type === "scheduled_refresh_summary" && event.outcome === "error") {
    return {
      action: "resync",
      hint: "立即重新触发全量同步，确认 OpenViking 和 Ollama 健康后观察队列。",
      label: "立即重新同步",
    };
  }
  if (event.event_type === "manual_rebuild_index" && event.outcome === "error") {
    return {
      action: "rebuild_index",
      hint: "重新排队并重建索引；如果仍失败，请检查 OpenViking 日志。",
      label: "重试重建",
    };
  }
  if (event.event_type === "openviking_breaker_tripped") {
    return { hint: "OpenViking 熔断已打开；确认进程健康后稍后重试。" };
  }
  if (event.event_type === "openviking_health_failed") {
    return { hint: "OpenViking 进程未通过健康检查；请查看 OpenViking 服务日志和网络/依赖下载状态。" };
  }
  if (event.event_type === "openviking_restart_detected") {
    return { hint: "进程已重启；如果频繁出现，请检查 OpenViking 日志。" };
  }
  return { hint: "查看事件详情和相关服务日志后重试。" };
}

function eventReadableName(
  event: OpenVikingDashboardEvent,
  payload: Record<string, unknown> | null,
) {
  return (
    stringFromUnknown(payload?.name) ??
    stringFromUnknown(payload?.title) ??
    readablePathFromPayload(payload) ??
    event.source_id ??
    event.source_type ??
    "system"
  );
}

function eventErrorText(
  event: OpenVikingDashboardEvent,
  payload: Record<string, unknown> | null,
) {
  if (event.outcome !== "warning" && event.outcome !== "error") {
    return null;
  }
  return (
    stringFromUnknown(payload?.error) ??
    stringFromUnknown(payload?.detail) ??
    stringFromUnknown(payload?.message) ??
    stringFromUnknown(payload?.reason) ??
    null
  );
}

function payloadSummary(payload: Record<string, unknown> | null) {
  if (payload) {
    const pairs = Object.entries(payload)
      .filter(([key]) => !["detail", "error", "message", "reason"].includes(key))
      .slice(0, 4)
      .map(([key, value]) => `${key}=${String(value)}`);
    if (pairs.length > 0) {
      return pairs.join(" · ");
    }
  }
  return null;
}

function eventPayloadText(payload: unknown) {
  if (payload === null || payload === undefined) {
    return null;
  }
  if (typeof payload === "string") {
    return payload;
  }
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function displayNumber(value: unknown) {
  return numberFromUnknown(value)?.toString() ?? EMPTY_VALUE;
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

function modelBackendValue(status: OpenVikingStatusResponse) {
  if (!status.embedding) {
    return EMPTY_VALUE;
  }
  return `${status.embedding.provider} / ${status.embedding.model}`;
}

function hasConfiguredOllamaDependency(
  status: OpenVikingStatusResponse,
): status is OpenVikingStatusResponse & {
  ollama: NonNullable<OpenVikingStatusResponse["ollama"]> & { configured: true };
} {
  return status.ollama?.configured === true;
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

function copyToClipboard(value: string, label: string, feedback: DashboardFeedback) {
  void copyTextToClipboard(value)
    .then(() => feedback.showSuccess(`${label}已复制`))
    .catch((error: unknown) =>
      feedback.showError(`复制${label}失败：${messageFromApiError(error)}`, { title: "复制失败" }),
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
