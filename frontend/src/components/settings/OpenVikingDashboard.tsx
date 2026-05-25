import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckCircle2, Database, ListChecks } from "lucide-react";

import {
  getOpenVikingEmbedding,
  getOpenVikingStatus,
  getOpenVikingTuning,
  listOpenVikingEvents,
  listOpenVikingSyncJobs,
} from "../../lib/api";
import type { OpenVikingDashboardEvent, OpenVikingSyncJob } from "../../types/api";

export function OpenVikingDashboard() {
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
    queryKey: ["admin-openviking-events"],
    queryFn: listOpenVikingEvents,
    refetchInterval: 5000,
  });
  const embeddingQuery = useQuery({
    queryKey: ["admin-openviking-embedding"],
    queryFn: getOpenVikingEmbedding,
  });
  const tuningQuery = useQuery({
    queryKey: ["admin-openviking-tuning"],
    queryFn: getOpenVikingTuning,
  });

  const status = statusQuery.data;
  const embedding = embeddingQuery.data;
  const tuning = tuningQuery.data;
  const running = status?.running ?? false;

  return (
    <div className="settings-stack">
      <section className="surface" aria-label="OpenViking 健康状态">
        <div className="section-title-row">
          <div>
            <h2>OpenViking RAG 状态</h2>
            <p>OpenViking 是增强能力；不可用时会话和 Wiki 仍按当前兜底路径运行。</p>
          </div>
        </div>
        {statusQuery.isLoading ? <p className="empty-note">正在读取 OpenViking 状态</p> : null}
        {statusQuery.isError ? <StatusError text="读取 OpenViking 状态失败" /> : null}
        {status ? (
          <>
            <div className="settings-runtime-summary" data-running={running}>
              <div className="settings-runtime-status">
                <span className="settings-runtime-status-icon">
                  {running ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
                </span>
                <div>
                  <span>运行状态</span>
                  <strong>{running ? "running" : "degraded"}</strong>
                </div>
              </div>
              <p>
                {running
                  ? "OpenViking server 已启动，后台同步任务可以使用语义索引。"
                  : "OpenViking 当前不可用；用户路径保持可用，admin 可从事件和日志定位原因。"}
              </p>
            </div>
            <div className="settings-diagnostic-grid">
              <Metric label="端口" value={status.port ?? "-"} />
              <Metric label="PID" value={status.pid ?? "-"} />
              <Metric label="版本" value={status.version ?? status.verified_version ?? "-"} />
              <Metric label="等待任务" value={status.queue?.pending ?? 0} />
              <Metric label="运行任务" value={status.queue?.running ?? 0} />
              <Metric label="失败任务" value={status.queue?.failed ?? 0} />
              <Metric
                label="OpenViking /health"
                value={status.health?.healthy ? "healthy" : "degraded"}
              />
              <Metric
                label="Ollama / 模型"
                value={status.ollama?.model_available ? "ready" : "missing"}
              />
              <Metric label="Embedding 模型" value={status.ollama?.required_model ?? "-"} />
            </div>
            {status.ollama ? (
              <PathBlock
                label="Ollama 模型列表"
                value={status.ollama.models.length > 0 ? status.ollama.models.join(", ") : "-"}
              />
            ) : null}
            <PathBlock label="配置文件" value={status.config_file} />
            <PathBlock label="工作目录" value={status.workspace_path} />
            <PathBlock label="日志文件" value={status.log_file} />
            {status.last_error ? <StatusError text={status.last_error} /> : null}
            {status.health?.error ? <StatusError text={status.health.error} /> : null}
            {status.ollama?.error ? <StatusError text={status.ollama.error} /> : null}
          </>
        ) : null}
      </section>

      <section className="surface" aria-label="OpenViking embedding 设置">
        <div className="section-title-row">
          <div>
            <h2>Embedding</h2>
            <p>当前激活的本机向量模型与并发上限。</p>
          </div>
          <Database aria-hidden="true" size={18} />
        </div>
        {embedding ? (
          <div className="settings-diagnostic-grid">
            <Metric label="Provider" value={embedding.provider} />
            <Metric label="Base URL" value={embedding.base_url} />
            <Metric label="模型" value={embedding.model} />
            <Metric label="维度" value={embedding.dimension ?? "-"} />
            <Metric label="最大并发" value={embedding.max_concurrent} />
            <Metric label="重建状态" value={embedding.rebuild_status} />
          </div>
        ) : (
          <p className="empty-note">正在读取 embedding 配置</p>
        )}
      </section>

      <section className="surface" aria-label="OpenViking 同步任务">
        <div className="section-title-row">
          <div>
            <h2>同步任务</h2>
            <p>最近的 OpenViking sync_jobs 状态。</p>
          </div>
          <ListChecks aria-hidden="true" size={18} />
        </div>
        <ul className="data-list settings-config-list">
          {(jobsQuery.data?.items ?? []).map((job) => (
            <SyncJobItem job={job} key={job.id} />
          ))}
        </ul>
        {jobsQuery.data?.items.length === 0 ? <p className="empty-note">暂无同步任务</p> : null}
      </section>

      <section className="surface" aria-label="OpenViking 事件流">
        <div className="section-title-row">
          <div>
            <h2>事件流</h2>
            <p>后台启动、同步、调优和错误事件。</p>
          </div>
          <Activity aria-hidden="true" size={18} />
        </div>
        <ul className="data-list settings-config-list">
          {(eventsQuery.data?.items ?? []).map((event) => (
            <EventItem event={event} key={event.id} />
          ))}
        </ul>
        {eventsQuery.data?.items.length === 0 ? <p className="empty-note">暂无 OpenViking 事件</p> : null}
      </section>

      <section className="surface" aria-label="OpenViking 调优参数">
        <div className="section-title-row">
          <div>
            <h2>调优参数</h2>
            <p>当前推荐预设：{tuning?.preset ?? "-"}</p>
          </div>
        </div>
        {tuning ? (
          <div className="settings-diagnostic-grid">
            {Object.entries(tuning.scopes).flatMap(([scope, rows]) =>
              rows.map((row) => (
                <Metric
                  key={`${scope}.${row.key}`}
                  label={`${scope}.${row.key}`}
                  value={row.value}
                />
              )),
            )}
          </div>
        ) : (
          <p className="empty-note">正在读取调优参数</p>
        )}
      </section>
    </div>
  );
}

function SyncJobItem({ job }: { job: OpenVikingSyncJob }) {
  return (
    <li className="settings-openviking-row">
      <div>
        <strong>{job.source_type}</strong>
        <span>{job.source_id}</span>
      </div>
      <Badge text={job.status} />
      {job.error ? <small>{job.error}</small> : null}
    </li>
  );
}

function EventItem({ event }: { event: OpenVikingDashboardEvent }) {
  return (
    <li className="settings-openviking-row">
      <div>
        <strong>{event.event_type}</strong>
        <span>{event.source_type ?? "system"}</span>
      </div>
      <Badge text={event.outcome} />
    </li>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="settings-diagnostic-item">
      <span>{label}</span>
      <strong>{value}</strong>
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
    </div>
  );
}

function StatusError({ text }: { text: string }) {
  return (
    <div className="settings-status-error">
      <AlertTriangle aria-hidden="true" size={16} />
      <span>{text}</span>
    </div>
  );
}

function Badge({ text }: { text: string }) {
  return <span className="settings-openviking-badge">{text}</span>;
}
