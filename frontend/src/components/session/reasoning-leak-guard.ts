export type ReasoningLeakGuardMode = "disabled" | "warn_only" | "mask_in_ui";

export interface ReasoningLeakDiagnostic {
  type: "reasoning_leak_detected";
  marker: string;
  mode: ReasoningLeakGuardMode;
  leakedLength: number;
  masked: boolean;
  rawText?: never;
}

export interface ReasoningLeakGuardResult {
  visibleText: string;
  diagnostic: ReasoningLeakDiagnostic | null;
}

const OPEN_TAG = "<think>";
const CLOSE_TAG = "</think>";

export function createReasoningLeakGuard(mode: ReasoningLeakGuardMode) {
  let buffer = "";
  let inside = false;
  let leakedLength = 0;
  let reported = false;

  function feed(text: string): ReasoningLeakGuardResult {
    if (mode === "disabled") {
      return { visibleText: text, diagnostic: null };
    }

    buffer += text;
    const output: string[] = [];
    let detected = false;

    while (buffer) {
      const lowered = buffer.toLowerCase();
      if (inside) {
        const closeIndex = lowered.indexOf(CLOSE_TAG);
        if (closeIndex === -1) {
          const keep = suffixLength(lowered, CLOSE_TAG);
          leakedLength += Math.max(0, buffer.length - keep);
          buffer = keep ? buffer.slice(-keep) : "";
          detected = true;
          break;
        }
        leakedLength += closeIndex;
        buffer = buffer.slice(closeIndex + CLOSE_TAG.length);
        inside = false;
        detected = true;
        continue;
      }

      if (mode === "mask_in_ui") {
        const closeIndex = lowered.indexOf(CLOSE_TAG);
        const openIndex = lowered.indexOf(OPEN_TAG);
        if (closeIndex !== -1 && (openIndex === -1 || closeIndex < openIndex)) {
          detected = true;
          output.push(buffer.slice(0, closeIndex));
          buffer = buffer.slice(closeIndex + CLOSE_TAG.length);
          continue;
        }
      }

      const openIndex = lowered.indexOf(OPEN_TAG);
      if (openIndex === -1) {
        const keep = suffixLength(lowered, OPEN_TAG);
        const closeKeep = mode === "mask_in_ui" ? suffixLength(lowered, CLOSE_TAG) : 0;
        const keepLength = Math.max(keep, closeKeep);
        if (mode === "mask_in_ui") {
          output.push(keepLength ? buffer.slice(0, -keepLength) : buffer);
        } else {
          output.push(buffer);
          buffer = "";
          break;
        }
        buffer = keepLength ? buffer.slice(-keepLength) : "";
        break;
      }

      detected = true;
      output.push(buffer.slice(0, openIndex));
      buffer = buffer.slice(openIndex + OPEN_TAG.length);
      inside = true;
    }

    const diagnostic =
      detected && !reported
        ? {
            type: "reasoning_leak_detected" as const,
            marker: "think",
            mode,
            leakedLength,
            masked: mode === "mask_in_ui",
          }
        : null;
    if (diagnostic) {
      reported = true;
    }

    return {
      visibleText: mode === "mask_in_ui" ? output.join("") : text,
      diagnostic,
    };
  }

  return { feed };
}

export function visibleContentFromLeakGuardResult(
  results: ReasoningLeakGuardResult[],
) {
  return results.map((result) => result.visibleText).join("");
}

function suffixLength(text: string, tag: string) {
  const max = Math.min(text.length, tag.length - 1);
  for (let length = max; length > 0; length -= 1) {
    if (tag.startsWith(text.slice(-length))) {
      return length;
    }
  }
  return 0;
}
