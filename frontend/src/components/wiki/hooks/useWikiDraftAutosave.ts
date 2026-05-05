import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { saveWikiDraft } from "../../../lib/wiki/api";
import type { WikiDocumentDetailRead } from "../../../types/wiki";

export function useWikiDraftAutosave({
  baselineBody,
  bodyMarkdown,
  enabled,
  nodeId,
  onSaved,
}: {
  baselineBody: string;
  bodyMarkdown: string;
  enabled: boolean;
  nodeId: number | null;
  onSaved?: (document: WikiDocumentDetailRead | null, savedBody: string) => void;
}) {
  const lastSavedRef = useRef(bodyMarkdown);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    lastSavedRef.current = baselineBody;
    setStatus("idle");
  }, [baselineBody, nodeId]);

  const mutation = useMutation({
    mutationFn: async (nextBody: string) => {
      if (nodeId == null) {
        return null;
      }
      return saveWikiDraft(nodeId, nextBody);
    },
    onMutate: () => {
      setStatus("saving");
    },
    onSuccess: (data, variables) => {
      lastSavedRef.current = variables;
      setStatus("saved");
      onSaved?.(data, variables);
    },
    onError: () => {
      setStatus("error");
    },
  });

  useEffect(() => {
    if (!enabled || nodeId == null) {
      return;
    }
    if (bodyMarkdown === lastSavedRef.current) {
      return;
    }
    const timer = window.setTimeout(() => {
      mutation.mutate(bodyMarkdown);
    }, 800);
    return () => {
      window.clearTimeout(timer);
    };
  }, [bodyMarkdown, enabled, mutation, nodeId]);

  return {
    autosaveStatus: status,
    markSavedBaseline(nextBody: string) {
      lastSavedRef.current = nextBody;
      setStatus("idle");
    },
  };
}
