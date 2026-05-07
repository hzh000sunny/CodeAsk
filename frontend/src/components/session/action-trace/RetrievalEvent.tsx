import { Database } from "lucide-react";

import type { ActionTraceEvent } from "./action-trace-model";

export function RetrievalEvent({ event }: { event: ActionTraceEvent }) {
  return (
    <>
      <Database aria-hidden="true" size={15} />
      <span>{event.detail}</span>
    </>
  );
}
