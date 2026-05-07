import { MessageCircleQuestion } from "lucide-react";

import type { ActionTraceEvent } from "./action-trace-model";

export function ClarificationEvent({ event }: { event: ActionTraceEvent }) {
  return (
    <>
      <MessageCircleQuestion aria-hidden="true" size={15} />
      <span>{event.detail}</span>
    </>
  );
}
