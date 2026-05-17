import type { ActionTraceEvent, EvidenceRef } from "./action-trace-model";

const SESSION_PATH_MARKER = "/agent_sessions/";
const SESSION_ABSOLUTE_PATH_PATTERN =
  /(?:[A-Za-z]:)?\/[^\s"'`<>|)]*\/agent_sessions\/[^\s"'`<>|)]+\/sess_[A-Za-z0-9_-]+(?:\/[^\s"'`<>|)]*)?/g;
const WINDOWS_ABSOLUTE_PATH_PATTERN =
  /\b[A-Za-z]:\\[^\s"'`<>|)]+/g;
const POSIX_ABSOLUTE_PATH_PATTERN =
  /(^|[\s"'`([{:=,])((?:\/(?:home|Users|var|tmp|opt|private|mnt|srv|root|etc|usr|run|data|Volumes|workspace)\b[^\s"'`<>|)]*))/g;

const HIDDEN_ABSOLUTE_PATH = "[外部绝对路径已隐藏]";

export function redactActionTraceEvent(event: ActionTraceEvent): ActionTraceEvent {
  return {
    ...event,
    title: redactTraceDisplayText(event.title),
    detail: redactTraceDisplayText(event.detail),
    detailMarkdown: event.detailMarkdown
      ? redactTraceDisplayText(event.detailMarkdown)
      : undefined,
    data: redactTraceDisplayValue(event.data),
    evidenceRefs: event.evidenceRefs?.map(redactEvidenceRef),
  };
}

export function redactTraceDisplayText(value: string): string {
  if (!value) {
    return value;
  }
  return value
    .replace(SESSION_ABSOLUTE_PATH_PATTERN, sessionRelativePath)
    .replace(WINDOWS_ABSOLUTE_PATH_PATTERN, HIDDEN_ABSOLUTE_PATH)
    .replace(POSIX_ABSOLUTE_PATH_PATTERN, (_match, prefix: string) => {
      return `${prefix}${HIDDEN_ABSOLUTE_PATH}`;
    });
}

export function redactTraceDisplayValue<T>(value: T): T {
  if (typeof value === "string") {
    return redactTraceDisplayText(value) as T;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactTraceDisplayValue(item)) as T;
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, child]) => [
        key,
        redactTraceDisplayValue(child),
      ]),
    ) as T;
  }
  return value;
}

function redactEvidenceRef(ref: EvidenceRef): EvidenceRef {
  return redactTraceDisplayValue(ref);
}

function sessionRelativePath(value: string) {
  const markerIndex = value.indexOf(SESSION_PATH_MARKER);
  if (markerIndex === -1) {
    return HIDDEN_ABSOLUTE_PATH;
  }
  const afterMarker = value.slice(markerIndex + SESSION_PATH_MARKER.length);
  const parts = afterMarker.split("/");
  const relativeParts = parts.slice(2).filter(Boolean);
  return relativeParts.length > 0 ? relativeParts.join("/") : ".";
}
