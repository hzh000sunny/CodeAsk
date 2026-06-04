import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Brain,
  ChevronRight,
  Database,
  FileText,
  HelpCircle,
  Loader2,
  Search,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import {
  actionTraceKindLabel,
  type ActionTraceEvent as ActionTraceEventModel,
} from "./action-trace/action-trace-model";

interface WorkingTimelineProps {
  events: ActionTraceEventModel[];
  /** Whether the owning turn is still streaming. Controls live styling + default-open. */
  live: boolean;
}

const KIND_ICONS: Record<string, LucideIcon> = {
  analysis: Brain,
  retrieval: Database,
  wiki_scope: Database,
  tool_call: Wrench,
  tool_result: Wrench,
  evidence: FileText,
  clarification: HelpCircle,
  assistant_action: Sparkles,
  runtime_status: Loader2,
  diagnostic: Search,
  warning: AlertTriangle,
  error: AlertCircle,
};

/**
 * Compact, collapsible record of what the agent did within a single turn —
 * the "investigation" threaded inline beneath the assistant's answer. The
 * full forensic detail still lives in the right-hand action-trace panel; this
 * view is the scannable story of the work.
 */
export function WorkingTimeline({ events, live }: WorkingTimelineProps) {
  const [open, setOpen] = useState(live);
  const stepsRef = useRef<HTMLOListElement | null>(null);

  // While the turn is live, keep the newest step in view inside the bounded
  // scroller so a turn with hundreds of tool calls never grows without limit.
  useEffect(() => {
    if (live && open && stepsRef.current) {
      stepsRef.current.scrollTop = stepsRef.current.scrollHeight;
    }
  }, [events.length, live, open]);

  if (events.length === 0) {
    if (!live) {
      return null;
    }
    return (
      <div className="working-timeline" data-live="true" data-empty="true">
        <div className="working-timeline-thinking" role="status">
          <Loader2 aria-hidden="true" size={14} className="spin" />
          <span>正在分析问题…</span>
        </div>
      </div>
    );
  }

  const metrics = summarize(events);
  const panelId = `working-timeline-${events[0]?.id ?? "turn"}`;

  return (
    <div className="working-timeline" data-live={live ? "true" : "false"}>
      <button
        aria-controls={panelId}
        aria-expanded={open}
        className="working-timeline-summary"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <ChevronRight
          aria-hidden="true"
          className="working-timeline-caret"
          data-open={open ? "true" : "false"}
          size={14}
        />
        <span className="working-timeline-label">
          {live ? "调查进行中" : "调查过程"}
        </span>
        <span className="working-timeline-metrics" aria-hidden={open}>
          {metrics.map((metric) => (
            <span
              className="working-timeline-metric"
              data-tone={metric.tone}
              key={metric.id}
            >
              <strong>{metric.value}</strong>
              {metric.label}
            </span>
          ))}
        </span>
      </button>
      {open ? (
        <ol className="working-timeline-steps" id={panelId} ref={stepsRef}>
          {events.map((event, index) => {
            const Icon = KIND_ICONS[String(event.kind)] ?? Search;
            const status = stepStatus(event, live, index === events.length - 1);
            return (
              <li
                className="working-timeline-step"
                data-status={status}
                key={event.id}
              >
                <span aria-hidden="true" className="working-timeline-dot" />
                <Icon
                  aria-hidden="true"
                  className="working-timeline-icon"
                  size={14}
                />
                <span className="working-timeline-step-body">
                  <span className="working-timeline-step-title">
                    <span className="working-timeline-step-kind">
                      {actionTraceKindLabel(event.kind)}
                    </span>
                    {event.title}
                  </span>
                  {event.detail ? (
                    <span className="working-timeline-step-detail">
                      {event.detail}
                    </span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </div>
  );
}

interface TimelineMetric {
  id: string;
  label: string;
  value: number;
  tone: "activity" | "evidence" | "error";
}

function summarize(events: ActionTraceEventModel[]): TimelineMetric[] {
  const tools = events.filter((event) =>
    ["tool_call", "tool_result"].includes(String(event.kind)),
  ).length;
  const evidence = events.filter(
    (event) =>
      event.kind === "evidence" || (event.evidenceRefs?.length ?? 0) > 0,
  ).length;
  const errors = events.filter(
    (event) => event.status === "error" || event.kind === "error",
  ).length;
  const metrics: TimelineMetric[] = [
    { id: "steps", label: "步", value: events.length, tone: "activity" },
  ];
  if (tools > 0) {
    metrics.push({ id: "tools", label: "工具", value: tools, tone: "activity" });
  }
  if (evidence > 0) {
    metrics.push({
      id: "evidence",
      label: "证据",
      value: evidence,
      tone: "evidence",
    });
  }
  if (errors > 0) {
    metrics.push({ id: "errors", label: "失败", value: errors, tone: "error" });
  }
  return metrics;
}

function stepStatus(
  event: ActionTraceEventModel,
  live: boolean,
  isLast: boolean,
): "running" | "success" | "error" | "info" {
  if (event.status === "error" || event.kind === "error") {
    return "error";
  }
  if (event.status === "running") {
    return live ? "running" : "info";
  }
  if (event.status === "success") {
    return "success";
  }
  // The trailing step of a still-streaming turn reads as in-flight.
  if (live && isLast) {
    return "running";
  }
  return "info";
}
