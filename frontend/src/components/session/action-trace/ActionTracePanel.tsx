import { useEffect, useRef } from "react";
import { Activity } from "lucide-react";

import { Badge } from "../../ui/badge";
import { ActionTraceEvent } from "./ActionTraceEvent";
import type { ActionTraceEvent as ActionTraceEventModel } from "./action-trace-model";

interface ActionTracePanelProps {
  events: ActionTraceEventModel[];
  isStreaming: boolean;
}

export function ActionTracePanel({ events, isStreaming }: ActionTracePanelProps) {
  const scrollRef = useRef<HTMLUListElement | null>(null);

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
        <ul className="action-trace-list action-trace-scroll" ref={scrollRef}>
          {events.map((event) => (
            <li
              data-action-trace-id={event.id}
              data-kind={event.kind}
              key={event.id}
            >
              <ActionTraceEvent event={event} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
