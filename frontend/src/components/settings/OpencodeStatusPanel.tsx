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
    <section
      className="surface opencode-card opencode-hero"
      data-running={running}
      aria-label="opencode 后端状态"
    >
      <header className="opencode-hero-head">
        <div className="opencode-signal" data-running={running} aria-hidden="true">
          <span className="opencode-signal-ring" />
          <span className="opencode-signal-core">
            <Power size={20} strokeWidth={2.4} />
          </span>
        </div>
        <div className="opencode-hero-text">
          <span className="opencode-hero-kicker">
            <Server aria-hidden="true" size={12} />
            opencode backend
          </span>
          <strong>{running ? "运行中" : "未运行"}</strong>
          <p>
            {statusQuery.isLoading
              ? "正在读取 opencode 状态…"
              : running
                ? "常驻进程已就绪，会话请求复用该 opencode server。"
                : "进程不可用，会话请求会返回后端不可用提示。"}
          </p>
        </div>
        {statusQuery.isError ? (
          <span className="opencode-hero-badge" data-tone="error">
            <AlertTriangle aria-hidden="true" size={13} />
            读取失败
          </span>
        ) : null}
      </header>

      {status ? (
        <>
          <div className="opencode-chip-strip">
            <Chip icon={Terminal} label="版本" value={status.version} mono />
            <Chip icon={Hash} label="PID" value={status.pid} mono />
            <Chip icon={Server} label="端口" value={status.port} mono />
            <Chip icon={Activity} label="活动会话" value={status.active_session_count} mono />
            <Chip icon={Clock3} label="健康检查" value={formatDateTime(status.last_health_at)} />
            <Chip icon={Hash} label="退出码" value={status.returncode} mono />
          </div>

          <div className="opencode-paths" aria-label="opencode 路径详情">
            <PathItem icon={Terminal} label="可执行文件" value={executablePath ?? "未知"} />
            {status.configured_bin && status.configured_bin !== executablePath ? (
              <PathItem icon={Terminal} label="配置命令" value={status.configured_bin} />
            ) : null}
            <PathItem icon={FileText} label="日志文件" value={status.log_file ?? "未知"} />
          </div>

          {status.last_error || status.last_error_code ? (
            <div className="opencode-status-line" data-tone="error">
              <AlertTriangle aria-hidden="true" size={15} />
              <span>
                {status.last_error_code ? `${status.last_error_code}：` : ""}
                {status.last_error ?? "opencode 运行异常"}
              </span>
            </div>
          ) : (
            <div className="opencode-status-line" data-tone="ok">
              <Check aria-hidden="true" size={15} />
              <span>最近未记录 opencode 错误</span>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}

function Chip({
  icon: Icon,
  label,
  value,
  mono = false,
}: {
  icon: typeof Activity;
  label: string;
  value: number | string | null | undefined;
  mono?: boolean;
}) {
  return (
    <div className="opencode-chip">
      <span className="opencode-chip-label">
        <Icon aria-hidden="true" size={12} />
        {label}
      </span>
      <strong className={mono ? "opencode-mono" : undefined}>{formatNullable(value)}</strong>
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
    <div className="opencode-path-item">
      <div className="opencode-path-label">
        <Icon aria-hidden="true" size={14} />
        <span>{label}</span>
      </div>
      <code className="opencode-mono" title={value}>
        {value}
      </code>
      <button
        aria-label={`复制 ${label}`}
        className="opencode-copy-button"
        disabled={!canCopy}
        onClick={() => void copyValue()}
        title={`复制${label}`}
        type="button"
      >
        {copyStatus === "已复制" ? (
          <Check aria-hidden="true" size={13} />
        ) : (
          <Copy aria-hidden="true" size={13} />
        )}
        <span>{copyStatus || "复制"}</span>
      </button>
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
