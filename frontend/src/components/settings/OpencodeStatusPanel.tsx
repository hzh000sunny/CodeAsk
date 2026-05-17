import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Check,
  Clock3,
  Copy,
  FileText,
  Hash,
  Power,
  Server,
  Terminal,
} from "lucide-react";

import { getOpencodeStatus } from "../../lib/api";
import { copyTextToClipboard } from "../session/session-clipboard";

export function OpencodeStatusPanel() {
  const statusQuery = useQuery({
    queryKey: ["admin-opencode-status"],
    queryFn: getOpencodeStatus,
    refetchInterval: 15_000,
  });
  const status = statusQuery.data;
  const running = status?.running === true;
  const executablePath = status?.resolved_bin ?? status?.configured_bin ?? null;

  return (
    <section className="surface" aria-label="opencode 后端状态">
      <div className="section-title">
        <Server aria-hidden="true" size={18} />
        <h2>opencode 后端状态</h2>
      </div>
      {statusQuery.isLoading ? <p className="empty-note">正在读取 opencode 状态</p> : null}
      {statusQuery.isError ? (
        <div className="settings-status-error">
          <AlertTriangle aria-hidden="true" size={16} />
          <span>读取 opencode 状态失败</span>
        </div>
      ) : null}
      {status ? (
        <>
          <div className="settings-runtime-summary" data-running={running}>
            <div className="settings-runtime-status">
              <span className="settings-runtime-status-icon">
                <Power aria-hidden="true" size={18} />
              </span>
              <div>
                <span>运行状态</span>
                <strong>{running ? "运行中" : "未运行"}</strong>
              </div>
            </div>
            <p>
              {running
                ? "opencode server 已启动，会话请求可以复用该常驻进程。"
                : "opencode server 当前不可用，会话请求会返回后端不可用提示。"}
            </p>
          </div>
          <div className="settings-diagnostic-grid">
            <StatusItem icon={Terminal} label="版本" value={status.version ?? "未知"} />
            <StatusItem icon={Hash} label="PID" value={formatNullable(status.pid)} />
            <StatusItem icon={Server} label="端口" value={formatNullable(status.port)} />
            <StatusItem
              icon={Activity}
              label="活动会话"
              value={formatNullable(status.active_session_count)}
            />
            <StatusItem
              icon={Clock3}
              label="健康检查"
              value={formatDateTime(status.last_health_at)}
            />
            <StatusItem
              icon={Hash}
              label="退出码"
              value={formatNullable(status.returncode)}
            />
          </div>
          <div className="settings-runtime-paths" aria-label="opencode 路径详情">
            <PathItem
              icon={Terminal}
              label="可执行文件"
              value={executablePath ?? "未知"}
            />
            {status.configured_bin && status.configured_bin !== executablePath ? (
              <PathItem
                icon={Terminal}
                label="配置命令"
                value={status.configured_bin}
              />
            ) : null}
            <PathItem
              icon={FileText}
              label="日志文件"
              value={status.log_file ?? "未知"}
            />
          </div>
        </>
      ) : null}
      {status?.last_error || status?.last_error_code ? (
        <div className="settings-status-error">
          <AlertTriangle aria-hidden="true" size={16} />
          <span>
            {status.last_error_code ? `${status.last_error_code}：` : ""}
            {status.last_error ?? "opencode 运行异常"}
          </span>
        </div>
      ) : status ? (
        <div className="settings-status-ok">
          <Activity aria-hidden="true" size={16} />
          <span>最近未记录 opencode 错误</span>
        </div>
      ) : null}
    </section>
  );
}

function StatusItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  return (
    <div className="settings-diagnostic-item">
      <span>
        <Icon aria-hidden="true" size={14} />
        {label}
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function PathItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
}) {
  const [copyStatus, setCopyStatus] = useState("");
  const timeoutRef = useRef<number | null>(null);
  const canCopy = value !== "未知";

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  async function copyValue() {
    if (!canCopy) {
      return;
    }
    try {
      await copyTextToClipboard(value);
      setCopyStatus("已复制");
    } catch {
      setCopyStatus("复制失败");
    }
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = window.setTimeout(() => {
      setCopyStatus("");
      timeoutRef.current = null;
    }, 1600);
  }

  return (
    <div className="settings-runtime-path-item">
      <div className="settings-runtime-path-label">
        <Icon aria-hidden="true" size={15} />
        <span>{label}</span>
      </div>
      <code title={value}>{value}</code>
      <div className="settings-runtime-path-action">
        <button
          aria-label={`复制 ${label}`}
          className="settings-runtime-copy-button"
          disabled={!canCopy}
          onClick={() => void copyValue()}
          title={`复制${label}`}
          type="button"
        >
          {copyStatus === "已复制" ? (
            <Check aria-hidden="true" size={14} />
          ) : (
            <Copy aria-hidden="true" size={14} />
          )}
          <span>{copyStatus || "复制"}</span>
        </button>
      </div>
    </div>
  );
}

function formatNullable(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "未知";
  }
  return String(value);
}

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "未知";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
