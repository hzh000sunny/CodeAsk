import { CheckCircle2, XCircle } from "lucide-react";

import type { ActionTraceEvent } from "./action-trace-model";

export function ToolResultEvent({ event }: { event: ActionTraceEvent }) {
  const Icon = event.status === "error" ? XCircle : CheckCircle2;
  return (
    <>
      <Icon aria-hidden="true" size={15} />
      <span>{event.detail}</span>
    </>
  );
}
