import { useEffect, useRef, useState } from "react";

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
  const actionNoticeTimeoutRef = useRef<number | null>(null);
  const [actionNotice, setActionNotice] = useState("");
  const [copiedSessionId, setCopiedSessionId] = useState<string | null>(null);

  useEffect(() => {
    setCopiedSessionId(null);
    setActionNotice("");
    if (copyToastTimeoutRef.current) {
      window.clearTimeout(copyToastTimeoutRef.current);
      copyToastTimeoutRef.current = null;
    }
    clearActionNoticeTimer();
  }, [selectedSessionId]);

  useEffect(() => {
    return () => {
      if (copyToastTimeoutRef.current) {
        window.clearTimeout(copyToastTimeoutRef.current);
      }
      clearActionNoticeTimer();
    };
  }, []);

  function clearActionNoticeTimer() {
    if (actionNoticeTimeoutRef.current) {
      window.clearTimeout(actionNoticeTimeoutRef.current);
      actionNoticeTimeoutRef.current = null;
    }
  }

  function showActionNotice(message: string) {
    clearActionNoticeTimer();
    setActionNotice(message);
    actionNoticeTimeoutRef.current = window.setTimeout(() => {
      setActionNotice("");
      actionNoticeTimeoutRef.current = null;
    }, 2800);
  }

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
    actionNotice,
    copiedSessionId,
    copySessionId,
    showActionNotice,
  };
}
