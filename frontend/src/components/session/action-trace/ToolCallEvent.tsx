import { Wrench } from "lucide-react";

import type { ActionTraceEvent } from "./action-trace-model";

export function ToolCallEvent({ event }: { event: ActionTraceEvent }) {
  return (
    <>
      <Wrench aria-hidden="true" size={15} />
      <span>{event.detail}</span>
    </>
  );
}
