import { useEffect, useRef, useState } from "react";

import { useAppFeedback } from "../feedback/AppFeedback";
import type { SessionResponse } from "../../types/api";
import { copyTextToClipboard } from "./session-clipboard";

export function useSessionNotices({
  selected,
  selectedSessionId,
}: {
  selected: SessionResponse | null;
  selectedSessionId: string;
}) {
  const copyToastTimeoutRef = useRef<number | null>(null);
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);
  const { showError, showSuccess } = useAppFeedback();

  useEffect(() => {
    setCopiedSessionId(null);
    if (copyToastTimeoutRef.current) {
      window.clearTimeout(copyToastTimeoutRef.current);
      copyToastTimeoutRef.current = null;
    }
  }, [selectedSessionId]);

  useEffect(() => {
    return () => {
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
    };
  }, []);

  async function copySessionId() {
    if (!selected) {
      return;
    }
    try {
      await copyTextToClipboard(selected.id);
      setCopiedSessionId(selected.id);
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
      copyToastTimeoutRef.current = window.setTimeout(() => {
        setCopiedSessionId(null);
        copyToastTimeoutRef.current = null;
      }, 1000);
    } catch {
      setCopiedSessionId(null);
    }
  }

  return {
    copiedSessionId,
    copySessionId,
    showActionNotice: (message: string, tone: "success" | "error" = "success") => {
      if (tone === "error") {
        showError(message);
        return;
      }
      showSuccess(message);
    },
  };
}
