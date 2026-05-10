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

      const openIndex = lowered.indexOf(OPEN_TAG);
      if (openIndex === -1) {
        const keep = suffixLength(lowered, OPEN_TAG);
        const visible = keep ? buffer.slice(0, -keep) : buffer;
        if (mode === "mask_in_ui") {
          output.push(visible);
        } else {
          output.push(buffer);
          buffer = "";
          break;
        }
        buffer = keep ? buffer.slice(-keep) : "";
        break;
      }

      detected = true;
      output.push(buffer.slice(0, openIndex));
      buffer = buffer.slice(openIndex + OPEN_TAG.length);
      inside = true;
    }

    return {
      visibleText: mode === "mask_in_ui" ? output.join("") : text,
      diagnostic: detected
        ? {
            type: "reasoning_leak_detected",
            marker: "think",
            mode,
            leakedLength,
            masked: mode === "mask_in_ui",
          }
        : null,
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
