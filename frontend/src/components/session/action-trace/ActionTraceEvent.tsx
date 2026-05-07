import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Brain, ChevronDown, X } from "lucide-react";

import { MarkdownRenderer } from "../../ui/MarkdownRenderer";
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

export function ActionTraceEvent({ event }: { event: ActionTraceEventModel }) {
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
        aria-label={`${event.title} 详情`}
        className="action-trace-card"
        data-status={event.status ?? "info"}
        onClick={(clickEvent) => openPreview(clickEvent.currentTarget)}
        type="button"
      >
        <span className="action-trace-card-title">
          <strong>{event.title}</strong>
          <ChevronDown aria-hidden="true" size={14} />
        </span>
        <span className="action-trace-card-detail">{renderEventDetail(event)}</span>
      </button>
      {preview
        ? createPortal(
            <ActionTracePreview
              event={event}
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
