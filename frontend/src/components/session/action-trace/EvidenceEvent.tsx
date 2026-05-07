import { FileSearch } from "lucide-react";

import { evidenceLabel, type ActionTraceEvent } from "./action-trace-model";

export function EvidenceEvent({ event }: { event: ActionTraceEvent }) {
  const labels = (event.evidenceRefs ?? []).map(evidenceLabel).slice(0, 2);
  return (
    <>
      <FileSearch aria-hidden="true" size={15} />
      <span>{labels.length > 0 ? labels.join(" · ") : event.detail}</span>
    </>
  );
}
