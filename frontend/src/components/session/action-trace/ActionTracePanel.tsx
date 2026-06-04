import { useEffect, useRef } from "react";
import { Activity, ChevronRight } from "lucide-react";

import { Badge } from "../../ui/badge";
import { ActionTraceEvent } from "./ActionTraceEvent";
import type { ActionTraceEvent as ActionTraceEventModel } from "./action-trace-model";

interface ActionTracePanelProps {
  events: ActionTraceEventModel[];
  isStreaming: boolean;
}

export function ActionTracePanel({ events, isStreaming }: ActionTracePanelProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const latestEvent = events.at(-1);
    if (!latestEvent) {
      return;
    }
    scrollRef.current
      ?.querySelector(`[data-action-trace-id="${latestEvent.id}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [events]);

  return (
    <section className="action-trace-section">
      <div className="panel-heading">
        <h2>Agent 行动轨迹</h2>
        <Badge>{isStreaming ? "运行中" : "就绪"}</Badge>
      </div>
      {events.length === 0 ? (
        <div className="action-trace-empty">
          <Activity aria-hidden="true" size={18} />
          <p>发送问题后，这里会展示模型实际使用的上下文和工具动作。</p>
        </div>
      ) : (
        <div className="action-trace-list action-trace-scroll" ref={scrollRef}>
          {groupActionTraceEvents(events).map((group, index, groups) => {
            // Routine counts read as one quiet gray run (zeros dropped); only
            // warnings/failures earn a small tinted flag.
            const countsText = group.summaryItems
              .filter(
                (item) =>
                  item.tone !== "warning" &&
                  item.tone !== "error" &&
                  item.value > 0,
              )
              .map((item) => `${item.value} ${item.label}`)
              .join(" · ");
            const flags = group.summaryItems.filter(
              (item) =>
                (item.tone === "warning" || item.tone === "error") &&
                item.value > 0,
            );
            return (
              <details
                className="action-trace-turn"
                key={group.id}
                open={index === groups.length - 1}
              >
                <summary className="action-trace-turn-heading">
                  <span className="action-trace-turn-headline">
                    <ChevronRight
                      aria-hidden="true"
                      className="action-trace-turn-caret"
                      size={14}
                    />
                    <span className="action-trace-turn-label">{group.label}</span>
                  </span>
                  <span
                    className="action-trace-turn-summary"
                    aria-label={`${group.label} 摘要`}
                  >
                    {countsText ? (
                      <span className="action-trace-turn-counts">{countsText}</span>
                    ) : null}
                    {flags.map((flag) => (
                      <span
                        className="action-trace-turn-flag"
                        data-tone={flag.tone}
                        key={flag.id}
                      >
                        <strong>{flag.value}</strong>
                        {flag.label}
                      </span>
                    ))}
                  </span>
                </summary>
                <ul className="action-trace-turn-list">
                  {group.events.map((event) => (
                    <li
                      data-action-trace-id={event.id}
                      data-kind={event.kind}
                      key={event.id}
                    >
                      <ActionTraceEvent event={event} />
                    </li>
                  ))}
                </ul>
              </details>
            );
          })}
        </div>
      )}
    </section>
  );
}

function groupActionTraceEvents(events: ActionTraceEventModel[]) {
  const groups: Array<{
    id: string;
    events: ActionTraceEventModel[];
    label: string;
    summaryItems: Array<{
      id: string;
      label: string;
      value: number;
      tone: "neutral" | "activity" | "evidence" | "warning" | "error";
    }>;
  }> = [];
  const groupIndexById = new Map<string, number>();

  for (const event of events) {
    const groupId = event.turnId ?? "unassigned";
    let groupIndex = groupIndexById.get(groupId);
    if (groupIndex === undefined) {
      groupIndex = groups.length;
      groupIndexById.set(groupId, groupIndex);
      groups.push({
        id: groupId,
        events: [],
        label: groupId.startsWith("live_") ? "本轮" : `第 ${groupIndex + 1} 轮`,
        summaryItems: [],
      });
    }
    groups[groupIndex].events.push(event);
  }

  return groups.map((group) => {
    const toolCount = group.events.filter((event) =>
      ["tool_call", "tool_result"].includes(String(event.kind)),
    ).length;
    const errorCount = group.events.filter(
      (event) => event.status === "error" || event.kind === "error",
    ).length;
    const evidenceCount = group.events.filter(
      (event) =>
        event.kind === "evidence" || (event.evidenceRefs?.length ?? 0) > 0,
    ).length;
    const warningCount = group.events.filter((event) => {
      const warnings = event.data?.warnings;
      return Array.isArray(warnings) && warnings.length > 0;
    }).length;
    const codeReadCount = group.events.filter(
      (event) => event.data?.tool_name === "read_code_file",
    ).length;
    return {
      ...group,
      summaryItems: [
        {
          id: "actions",
          label: "动作",
          value: group.events.length,
          tone: "activity",
        },
        {
          id: "tools",
          label: "工具",
          value: toolCount,
          tone: "neutral",
        },
        {
          id: "evidence",
          label: "证据",
          value: evidenceCount,
          tone: "evidence",
        },
        {
          id: "code",
          label: "读码",
          value: codeReadCount,
          tone: "neutral",
        },
        {
          id: "warnings",
          label: "提醒",
          value: warningCount,
          tone: "warning",
        },
        {
          id: "errors",
          label: "失败",
          value: errorCount,
          tone: "error",
        },
      ],
    };
  });
}
