import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileText,
  LoaderCircle,
  MessageSquareText,
  Pencil,
  Trash2,
  X,
  XCircle,
} from "lucide-react";

import type { RuntimeInsight, RuntimeStage } from "./session-model";
import type { AttachmentResponse } from "../../types/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

interface InvestigationPanelProps {
  attachments: AttachmentResponse[];
  insights: RuntimeInsight[];
  isLoadingAttachments: boolean;
  stages: RuntimeStage[];
  isStreaming: boolean;
  onDescribeAttachment: (attachment: AttachmentResponse) => void;
  onDeleteAttachment: (attachment: AttachmentResponse) => void;
  onRenameAttachment: (attachment: AttachmentResponse) => void;
}

export function InvestigationPanel({
  attachments,
  insights,
  isLoadingAttachments,
  isStreaming,
  onDescribeAttachment,
  onDeleteAttachment,
  onRenameAttachment,
  stages,
}: InvestigationPanelProps) {
  const stageScrollRef = useRef<HTMLDivElement | null>(null);
  const insightScrollRef = useRef<HTMLUListElement | null>(null);
  const [preview, setPreview] = useState<{
    insight: RuntimeInsight;
    left: number;
    maxHeight: number;
    placement: "left" | "right" | "below";
    top: number;
  } | null>(null);

  useEffect(() => {
    const currentStage =
      stages.find((stage) => stage.status === "active") ??
      [...stages].reverse().find((stage) => stage.status !== "pending");
    if (!currentStage) {
      return;
    }
    stageScrollRef.current
      ?.querySelector(`[data-stage-key="${currentStage.key}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [stages]);

  useEffect(() => {
    const latestInsight = insights.at(-1);
    if (!latestInsight) {
      return;
    }
    insightScrollRef.current
      ?.querySelector(`[data-insight-id="${latestInsight.id}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [insights]);

  useEffect(() => {
    if (!preview) {
      return;
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setPreview(null);
      }
    }

    function closeOnOutsideClick(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      if (target.closest(".insight-popover, .insight-card")) {
        return;
      }
      setPreview(null);
    }

    function closeOnResize() {
      setPreview(null);
    }

    window.addEventListener("keydown", closeOnEscape);
    window.addEventListener("pointerdown", closeOnOutsideClick);
    window.addEventListener("resize", closeOnResize);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      window.removeEventListener("pointerdown", closeOnOutsideClick);
      window.removeEventListener("resize", closeOnResize);
    };
  }, [preview]);

  function openPreview(insight: RuntimeInsight, target: HTMLButtonElement) {
    const rect = target.getBoundingClientRect();
    const width = Math.min(380, window.innerWidth - 24);
    const gap = 12;
    const verticalTop = Math.max(
      12,
      Math.min(rect.top - 4, window.innerHeight - 240),
    );
    const maxHeight = Math.max(160, window.innerHeight - verticalTop - 12);
    const canOpenLeft = rect.left >= width + gap + 12;
    const canOpenRight = window.innerWidth - rect.right >= width + gap + 12;

    if (canOpenLeft) {
      setPreview({
        insight,
        left: rect.left - width - gap,
        maxHeight,
        placement: "left",
        top: verticalTop,
      });
      return;
    }

    if (canOpenRight) {
      setPreview({
        insight,
        left: rect.right + gap,
        maxHeight,
        placement: "right",
        top: verticalTop,
      });
      return;
    }

    setPreview({
      insight,
      left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      maxHeight: Math.max(160, window.innerHeight - rect.bottom - gap - 12),
      placement: "below",
      top: Math.max(12, Math.min(rect.bottom + gap, window.innerHeight - 340)),
    });
  }

  return (
    <aside className="progress-panel" role="region" aria-label="调查进度">
      <div className="panel-heading">
        <h2>调查进度</h2>
        <Badge>{isStreaming ? "运行中" : "Agent Runtime"}</Badge>
      </div>
      <div className="progress-stage-scroll" ref={stageScrollRef}>
        <ol className="stage-list">
          {stages.map((stage) => (
            <StageItem key={stage.key} stage={stage} />
          ))}
        </ol>
      </div>
      <section className="insight-section" aria-label="运行事件">
        <div className="panel-subheading">
          <Activity aria-hidden="true" size={16} />
          <h3>运行事件</h3>
        </div>
        {insights.length === 0 ? (
          <p className="empty-note">暂无运行事件</p>
        ) : (
          <ul className="insight-list insight-scroll" ref={insightScrollRef}>
            {insights.map((insight) => (
              <li
                data-insight-id={insight.id}
                data-kind={insight.kind}
                key={insight.id}
              >
                <button
                  aria-label={`${insight.title} 详情`}
                  className="insight-card"
                  onClick={(event) => openPreview(insight, event.currentTarget)}
                  type="button"
                >
                  <strong>{insight.title}</strong>
                  <span>{insight.detail}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section
        className="attachment-section"
        role="region"
        aria-label="会话数据"
      >
        <div className="panel-subheading">
          <FileText aria-hidden="true" size={16} />
          <h3>会话数据</h3>
        </div>
        {isLoadingAttachments ? (
          <p className="empty-note">正在加载会话数据</p>
        ) : null}
        {!isLoadingAttachments && attachments.length === 0 ? (
          <p className="empty-note">暂无上传数据</p>
        ) : null}
        {attachments.length > 0 ? (
          <ul className="attachment-list attachment-scroll">
            {attachments.map((attachment) => (
              <li key={attachment.id}>
                <div className="attachment-summary">
                  <strong>{attachment.display_name}</strong>
                  <span>
                    {attachment.kind} ·{" "}
                    {formatAttachmentSize(attachment.size_bytes)} ·{" "}
                    {shortAttachmentId(attachment.id)}
                  </span>
                  {attachment.original_filename &&
                  attachment.original_filename !== attachment.display_name ? (
                    <span>原名 {attachment.original_filename}</span>
                  ) : null}
                  {attachment.description ? (
                    <span className="attachment-description">
                      {attachment.description}
                    </span>
                  ) : null}
                </div>
                <div className="row-actions">
                  <Button
                    aria-label={`编辑用途说明 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<MessageSquareText size={15} />}
                    onClick={() => onDescribeAttachment(attachment)}
                    title={`编辑用途说明 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                  <Button
                    aria-label={`重命名 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<Pencil size={15} />}
                    onClick={() => onRenameAttachment(attachment)}
                    title={`重命名 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                  <Button
                    aria-label={`删除 ${attachment.display_name}`}
                    className="icon-only"
                    icon={<Trash2 size={15} />}
                    onClick={() => onDeleteAttachment(attachment)}
                    title={`删除 ${attachment.display_name}`}
                    type="button"
                    variant="quiet"
                  />
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      {preview
        ? createPortal(
            <EventPreviewPopover
              insight={preview.insight}
              left={preview.left}
              maxHeight={preview.maxHeight}
              onClose={() => setPreview(null)}
              placement={preview.placement}
              top={preview.top}
            />,
            document.body,
          )
        : null}
    </aside>
  );
}

function StageItem({ stage }: { stage: RuntimeStage }) {
  const Icon =
    stage.status === "done"
      ? CheckCircle2
      : stage.status === "active"
        ? LoaderCircle
        : stage.status === "error"
          ? XCircle
          : Clock3;

  return (
    <li
      className="stage-item"
      data-done={stage.status === "done"}
      data-stage-key={stage.key}
      data-status={stage.status}
    >
      <Icon aria-hidden="true" size={17} />
      <div>
        <strong>{stage.label}</strong>
        <span>{stage.detail}</span>
      </div>
    </li>
  );
}

function EventPreviewPopover({
  insight,
  left,
  maxHeight,
  onClose,
  placement,
  top,
}: {
  insight: RuntimeInsight;
  left: number;
  maxHeight: number;
  onClose: () => void;
  placement: "left" | "right" | "below";
  top: number;
}) {
  return (
    <section
      aria-label="运行事件详情"
      aria-modal="false"
      className="insight-popover"
      data-placement={placement}
      role="dialog"
      style={{ left, maxHeight, top }}
    >
      <div className="insight-popover-header">
        <span>{eventKindLabel(insight.kind)}</span>
        <button
          aria-label="关闭运行事件详情"
          onClick={onClose}
          title="关闭"
          type="button"
        >
          <X aria-hidden="true" size={14} />
        </button>
      </div>
      <strong>{insight.title}</strong>
      <p>{insight.detail}</p>
      <small>ID · {insight.id}</small>
    </section>
  );
}

function eventKindLabel(kind: string) {
  if (kind === "scope") {
    return "范围判断";
  }
  if (kind === "sufficiency") {
    return "充分性判断";
  }
  if (kind === "tool") {
    return "工具事件";
  }
  if (kind === "evidence") {
    return "证据";
  }
  if (kind === "error") {
    return "错误";
  }
  return "运行事件";
}

function shortAttachmentId(id: string) {
  return id.length <= 8 ? id : id.slice(-8);
}

function formatAttachmentSize(sizeBytes: number | null | undefined) {
  if (typeof sizeBytes !== "number") {
    return "未知大小";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}
