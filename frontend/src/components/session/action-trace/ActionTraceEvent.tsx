import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Brain, ChevronDown, Copy, X } from "lucide-react";

import { MarkdownRenderer } from "../../ui/MarkdownRenderer";
import { copyTextToClipboard } from "../session-clipboard";
import { ClarificationEvent } from "./ClarificationEvent";
import { EvidenceEvent } from "./EvidenceEvent";
import { RetrievalEvent } from "./RetrievalEvent";
import { ToolCallEvent } from "./ToolCallEvent";
import { ToolResultEvent } from "./ToolResultEvent";
import {
  actionTraceKindLabel,
  evidenceLabel,
  type ActionTraceEvent as ActionTraceEventModel,
} from "./action-trace-model";
import { redactActionTraceEvent } from "./path-redaction";

export function ActionTraceEvent({ event }: { event: ActionTraceEventModel }) {
  const displayEvent = redactActionTraceEvent(event);
  const [preview, setPreview] = useState<{
    left: number;
    maxHeight: number;
    placement: "left" | "right" | "below";
    top: number;
  } | null>(null);

  useEffect(() => {
    function closeWhenAnotherEventOpens(openEvent: Event) {
      const detail = (openEvent as CustomEvent<{ id?: string }>).detail;
      if (detail?.id !== event.id) {
        setPreview(null);
      }
    }

    window.addEventListener("codeask:action-trace-open", closeWhenAnotherEventOpens);
    return () => {
      window.removeEventListener(
        "codeask:action-trace-open",
        closeWhenAnotherEventOpens,
      );
    };
  }, [event.id]);

  function openPreview(target: HTMLButtonElement) {
    window.dispatchEvent(
      new CustomEvent("codeask:action-trace-open", { detail: { id: event.id } }),
    );
    const rect = target.getBoundingClientRect();
    const width = Math.min(400, window.innerWidth - 24);
    const gap = 12;
    const verticalTop = Math.max(
      12,
      Math.min(rect.top - 4, window.innerHeight - 240),
    );
    const maxHeight = Math.max(180, window.innerHeight - verticalTop - 12);
    const canOpenLeft = rect.left >= width + gap + 12;
    const canOpenRight = window.innerWidth - rect.right >= width + gap + 12;

    if (canOpenLeft) {
      setPreview({
        left: rect.left - width - gap,
        maxHeight,
        placement: "left",
        top: verticalTop,
      });
      return;
    }

    if (canOpenRight) {
      setPreview({
        left: rect.right + gap,
        maxHeight,
        placement: "right",
        top: verticalTop,
      });
      return;
    }

    setPreview({
      left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      maxHeight: Math.max(180, window.innerHeight - rect.bottom - gap - 12),
      placement: "below",
      top: Math.max(12, Math.min(rect.bottom + gap, window.innerHeight - 340)),
    });
  }

  return (
    <>
      <button
        aria-label={`${displayEvent.title} 详情`}
        className="action-trace-card"
        data-status={event.status ?? "info"}
        onClick={(clickEvent) => openPreview(clickEvent.currentTarget)}
        type="button"
      >
        <span className="action-trace-card-title">
          <strong>{displayEvent.title}</strong>
          <ChevronDown aria-hidden="true" size={14} />
        </span>
        <span className="action-trace-card-detail">
          {renderEventDetail(displayEvent)}
        </span>
      </button>
      {preview
        ? createPortal(
            <ActionTracePreview
              event={displayEvent}
              left={preview.left}
              maxHeight={preview.maxHeight}
              onClose={() => setPreview(null)}
              placement={preview.placement}
              top={preview.top}
            />,
            document.body,
          )
        : null}
    </>
  );
}

function renderEventDetail(event: ActionTraceEventModel) {
  if (event.kind === "retrieval") {
    return <RetrievalEvent event={event} />;
  }
  if (event.kind === "tool_call") {
    return <ToolCallEvent event={event} />;
  }
  if (event.kind === "tool_result") {
    return <ToolResultEvent event={event} />;
  }
  if (event.kind === "evidence") {
    return <EvidenceEvent event={event} />;
  }
  if (event.kind === "clarification") {
    return <ClarificationEvent event={event} />;
  }
  return (
    <>
      <Brain aria-hidden="true" size={15} />
      <span>{event.detail}</span>
    </>
  );
}

function ActionTracePreview({
  event,
  left,
  maxHeight,
  onClose,
  placement,
  top,
}: {
  event: ActionTraceEventModel;
  left: number;
  maxHeight: number;
  onClose: () => void;
  placement: "left" | "right" | "below";
  top: number;
}) {
  return (
    <section
      aria-label="Agent 行动详情"
      aria-modal="false"
      className="action-trace-popover"
      data-placement={placement}
      role="dialog"
      style={{ left, maxHeight, top }}
    >
      <div className="action-trace-popover-header">
        <span>{actionTraceKindLabel(event.kind)}</span>
        <button
          aria-label="关闭行动详情"
          onClick={onClose}
          title="关闭"
          type="button"
        >
          <X aria-hidden="true" size={14} />
        </button>
      </div>
      <strong>{event.title}</strong>
      {event.detailMarkdown ? (
        <div className="action-trace-markdown">
          <MarkdownRenderer content={event.detailMarkdown} />
        </div>
      ) : (
        <p>{event.detail}</p>
      )}
      <ActionTraceDetailRows event={event} />
      {(event.evidenceRefs?.length ?? 0) > 0 ? (
        <ul className="action-trace-evidence-list">
          {event.evidenceRefs?.map((ref, index) => (
            <li key={`${ref.type ?? "ref"}_${ref.path ?? ref.node_id ?? index}`}>
              <span>{ref.type ?? "source"}</span>
              <strong>{evidenceLabel(ref)}</strong>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ActionTraceDetailRows({ event }: { event: ActionTraceEventModel }) {
  const rows = detailRowsForEvent(event);
  if (rows.length === 0) {
    return null;
  }
  return (
    <dl className="action-trace-detail-grid">
      {rows.map((row) => (
        <div className="action-trace-detail-row" key={row.label}>
          <dt>{row.label}</dt>
          <dd>
            <ActionTraceDetailValue label={row.label} value={row.value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ActionTraceDetailValue({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const [copyStatus, setCopyStatus] = useState("");
  const canCopy = value.length >= 24 || value.includes("\n") || value.includes("/");

  useEffect(() => {
    if (!copyStatus) {
      return;
    }
    const timer = window.setTimeout(() => {
      setCopyStatus("");
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  async function copyValue() {
    try {
      await copyTextToClipboard(value);
      setCopyStatus("已复制");
    } catch {
      setCopyStatus("复制失败");
    }
  }

  return (
    <span className="action-trace-detail-value">
      <span>{value}</span>
      {canCopy ? (
        <span className="action-trace-detail-copy">
          <button
            aria-label={`复制 ${label}`}
            className="action-trace-detail-copy-button"
            onClick={() => void copyValue()}
            title={`复制${label}`}
            type="button"
          >
            <Copy aria-hidden="true" size={13} />
          </button>
          {copyStatus ? (
            <span className="action-trace-detail-copy-toast" role="status">
              {copyStatus}
            </span>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}

function detailRowsForEvent(event: ActionTraceEventModel) {
  const data = event.data ?? {};
  const result = recordValue(data.result) ?? {};
  const resultData = recordValue(result.data) ?? {};
  const versionInfo = recordValue(data.version_info) ?? recordValue(result.version_info);
  const args =
    recordValue(data.arguments_summary) ?? recordValue(data.arguments);
  const rows: Array<{ label: string; value: string }> = [];
  addRow(rows, "所属轮次", event.turnId);
  addRow(rows, "发生时间", event.occurredAt);
  addRow(rows, "工具名称", stringValue(data.tool_name) ?? stringValue(data.name));
  addRow(rows, "调用编号", stringValue(data.tool_call_id) ?? stringValue(data.id));
  addRow(rows, "调用参数", args ? readableJson(args) : null);
  addRow(rows, "参数解析错误", stringValue(data.arguments_parse_error));
  addRow(rows, "原始参数", stringValue(data.raw_arguments));
  addRow(
    rows,
    "执行状态",
    data.ok === true || result.ok === true
      ? "成功"
      : data.ok === false || result.ok === false
        ? "失败"
        : null,
  );
  addRow(
    rows,
    "结果摘要",
    stringValue(data.summary) ??
      stringValue(result.summary) ??
      stringValue(resultData.summary) ??
      stringValue(result.message),
  );
  addRow(rows, "结果条数", numberDataLabel(data.items_count));
  addRow(rows, "结果预览", itemsPreviewLabel(data.items_preview));
  addRow(rows, "错误类型", stringValue(data.error_type) ?? stringValue(result.error));
  addRow(rows, "错误信息", stringValue(data.message) ?? stringValue(result.message));
  if (versionInfo) {
    addRow(rows, "范围来源", scopeSourceLabel(stringValue(versionInfo.scope_source)));
    addRow(rows, "特性", featureIdsLabel(versionInfo.feature_ids));
    addRow(rows, "仓库", codeRepoLabel(versionInfo));
    addRow(rows, "版本", stringValue(versionInfo.ref));
    addRow(rows, "提交", stringValue(versionInfo.commit));
  }
  addRow(rows, "提醒", warningsLabel(data.warnings, result.warnings));
  addRow(
    rows,
    "结果已截断",
    data.truncated === true || result.truncated === true ? "是" : null,
  );
  addRow(
    rows,
    "原始结果",
    stringValue(data.raw_result_ref) ?? stringValue(result.raw_result_ref),
  );
  addRow(
    rows,
    "结果规模",
    Array.isArray(resultData.hits) ? `${resultData.hits.length} 条命中` : null,
  );
  addRow(rows, "消息数", numberDataLabel(data.messages_count));
  addRow(rows, "可用工具数", numberDataLabel(data.tools_count));
  addRow(rows, "上下文长度", contextSizeLabel(data.context_size_chars));
  addRow(rows, "最近工具结果", recentToolResultsLabel(data.recent_tool_results));
  addRow(rows, "路径", stringValue(data.path) ?? stringValue(resultData.path));
  return rows;
}

function addRow(
  rows: Array<{ label: string; value: string }>,
  label: string,
  value: string | null | undefined,
) {
  if (value) {
    rows.push({ label, value });
  }
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberDataLabel(value: unknown) {
  const number = numberValue(value);
  return number === null ? null : String(number);
}

function contextSizeLabel(value: unknown) {
  const number = numberValue(value);
  return number === null ? null : `${number} 字符`;
}

function itemsPreviewLabel(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  return value.map((item) => readableUnknown(item)).join("\n");
}

function recentToolResultsLabel(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }
  return value.map((item) => readableUnknown(item)).join("\n");
}

function readableUnknown(value: unknown) {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function featureIdsLabel(value: unknown) {
  if (!Array.isArray(value)) {
    return null;
  }
  const ids = value.filter((item): item is number => Number.isInteger(item));
  return ids.length > 0 ? ids.join(", ") : null;
}

function scopeSourceLabel(value: string | null) {
  if (value === "feature_scope") {
    return "特性范围";
  }
  if (value === "explicit_user_repo") {
    return "用户显式仓库";
  }
  return value;
}

function codeRepoLabel(versionInfo: Record<string, unknown>) {
  const repoName = stringValue(versionInfo.repo_name);
  const repoId = stringValue(versionInfo.repo_id);
  if (repoName && repoId) {
    return `${repoName}(${repoId})`;
  }
  return repoName ?? repoId;
}

function readableJson(value: Record<string, unknown>) {
  if (Object.keys(value).length === 0) {
    return null;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function warningsLabel(...values: unknown[]) {
  for (const value of values) {
    if (!Array.isArray(value)) {
      continue;
    }
    const warnings = value.filter(
      (item): item is string => typeof item === "string" && item.length > 0,
    );
    if (warnings.length > 0) {
      return warnings.join(" | ");
    }
  }
  return null;
}
