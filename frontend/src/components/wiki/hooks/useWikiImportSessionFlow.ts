import { useEffect, useRef, useState } from "react";
import { useMutation, type QueryClient } from "@tanstack/react-query";

import {
  bulkResolveWikiImportSession,
  cancelWikiImportSession,
  createWikiImportSession,
  getWikiTree,
  getWikiImportSession,
  listWikiImportSessionItems,
  resolveWikiImportSessionItem,
  retryFailedWikiImportSession,
  retryWikiImportSessionItem,
  scanWikiImportSession,
  uploadWikiImportSessionItem,
} from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import type { WikiRouteState } from "../../../lib/wiki/routing";
import type { WikiTreeNodeRecord } from "../../../lib/wiki/tree";
import type {
  WikiImportSelectionItem,
  WikiImportSessionItemRead,
  WikiImportSessionItemsRead,
  WikiImportSessionRead,
  WikiSpaceRead,
} from "../../../types/wiki";
import { messageFromError } from "../../features/feature-utils";

interface UseWikiImportSessionFlowOptions {
  activeFeatureId: number | null;
  activeSpace: WikiSpaceRead | null;
  backgroundSession: { sessionId: number; featureId: number | null } | null;
  knowledgeRoot: WikiTreeNodeRecord | null;
  onBackgroundSessionChange?: (session: { sessionId: number; featureId: number | null } | null) => void;
  queryClient: QueryClient;
  onRouteChange: (patch: Partial<WikiRouteState>) => void;
  invalidateActiveFeatureTree: (featureId: number) => Promise<void>;
  onCompleted?: () => void;
}

export function useWikiImportSessionFlow({
  activeFeatureId,
  activeSpace,
  backgroundSession,
  knowledgeRoot,
  onBackgroundSessionChange,
  queryClient,
  onRouteChange,
  invalidateActiveFeatureTree,
  onCompleted,
}: UseWikiImportSessionFlowOptions) {
  const [importSession, setImportSession] = useState<WikiImportSessionRead | null>(null);
  const [importSessionItems, setImportSessionItems] = useState<WikiImportSessionItemsRead | null>(
    null,
  );
  const [importParent, setImportParent] = useState<WikiTreeNodeRecord | null>(null);
  const [importError, setImportError] = useState("");
  const [actionPendingKey, setActionPendingKey] = useState<string | null>(null);
  const cancelRequestedRef = useRef(false);
  const activeUploadItemIdRef = useRef<number | null>(null);

  function resetImportState() {
    setImportSession(null);
    setImportSessionItems(null);
    setImportParent(null);
    setImportError("");
    setActionPendingKey(null);
  }

  function openImportDialog(parent?: WikiTreeNodeRecord | null) {
    if (importSession?.status === "running") {
      setImportParent((current) => current ?? parent ?? knowledgeRoot ?? null);
      onRouteChange({ drawer: "import" });
      return;
    }
    resetImportState();
    setImportParent(parent ?? knowledgeRoot ?? null);
    onRouteChange({ drawer: "import" });
  }

  function closeImportDialog() {
    resetImportState();
    onRouteChange({ drawer: null });
  }

  function continueImportInBackground() {
    onRouteChange({ drawer: null });
  }

  async function refreshItems(sessionId: number) {
    const items = await listWikiImportSessionItems(sessionId);
    setImportSessionItems(items);
    return items;
  }

  async function refreshSession(sessionId: number) {
    const session = await getWikiImportSession(sessionId);
    setImportSession(session);
    return session;
  }

  function patchImportItem(
    itemId: number,
    updater: (item: WikiImportSessionItemRead) => WikiImportSessionItemRead,
  ) {
    setImportSessionItems((current) => {
      if (current == null) {
        return current;
      }
      return {
        items: current.items.map((item) => (item.id === itemId ? updater(item) : item)),
      };
    });
  }

  function replaceImportItem(nextItem: WikiImportSessionItemRead) {
    setImportSessionItems((current) => {
      if (current == null) {
        return { items: [nextItem] };
      }
      let found = false;
      const items = current.items.map((item) => {
        if (item.id !== nextItem.id) {
          return item;
        }
        found = true;
        return nextItem;
      });
      return {
        items: found ? items : [...items, nextItem],
      };
    });
  }

  async function finalizeCompletedSession(sessionId: number) {
    const items = await refreshItems(sessionId);
    const firstImportedDocumentNodeId =
      items.items.find((item) => item.item_kind === "document" && item.result_node_id != null)
        ?.result_node_id ?? null;
    if (activeFeatureId != null) {
      await invalidateActiveFeatureTree(activeFeatureId);
    }
    await queryClient.fetchQuery({
      queryKey: wikiQueryKeys.tree(null),
      queryFn: () => getWikiTree(null),
    });
    onCompleted?.();
    resetImportState();
    if (activeFeatureId != null && firstImportedDocumentNodeId != null) {
      onRouteChange({
        featureId: activeFeatureId,
        nodeId: firstImportedDocumentNodeId,
        mode: "view",
        drawer: null,
      });
      return;
    }
    onRouteChange({ drawer: null });
  }

  useEffect(() => {
    if (importSession?.status === "running" && importSession.id != null) {
      onBackgroundSessionChange?.({
        sessionId: importSession.id,
        featureId: activeFeatureId,
      });
      return;
    }
    onBackgroundSessionChange?.(null);
  }, [activeFeatureId, importSession?.id, importSession?.status, onBackgroundSessionChange]);

  useEffect(() => {
    if (!backgroundSession || importSession != null) {
      return;
    }
    if (activeFeatureId == null || backgroundSession.featureId !== activeFeatureId) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const session = await getWikiImportSession(backgroundSession.sessionId);
        const items = await listWikiImportSessionItems(backgroundSession.sessionId);
        if (cancelled) {
          return;
        }
        if (session.status === "running") {
          setImportSession(session);
          setImportSessionItems(items);
          return;
        }
        onBackgroundSessionChange?.(null);
      } catch {
        if (!cancelled) {
          onBackgroundSessionChange?.(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeFeatureId, backgroundSession, importSession, onBackgroundSessionChange]);

  const importSessionMutation = useMutation({
    mutationFn: async (payload: {
      files: File[];
      items: WikiImportSelectionItem[];
      mode: "markdown" | "directory";
    }) => {
      if (!activeSpace) {
        return null;
      }
      cancelRequestedRef.current = false;
      const session = await createWikiImportSession({
        spaceId: activeSpace.id,
        parentId: importParent?.id ?? knowledgeRoot?.id ?? null,
        mode: payload.mode,
      });
      setImportSession(session);
      setImportSessionItems({ items: [] });

      const scannedSession = await scanWikiImportSession(session.id, {
        items: payload.items.map((item) => ({
          relative_path: item.relativePath,
          item_kind: item.itemKind,
          included: item.included,
          ignore_reason: item.ignoreReason,
        })),
      });
      setImportSession(scannedSession);

      let items = await listWikiImportSessionItems(session.id);
      setImportSessionItems(items);

      const fileByPath = new Map(
        payload.items
          .filter((item) => item.included)
          .map((item) => [item.relativePath, item.file] as const),
      );
      let lastSession = scannedSession;

      for (const item of items.items) {
        if (cancelRequestedRef.current) {
          return { sessionId: session.id, status: "cancelled" as const };
        }
        if (item.status !== "pending") {
          continue;
        }
        const sourceFile = fileByPath.get(item.source_path);
        if (!sourceFile) {
          continue;
        }
        patchImportItem(item.id, (current) => ({
          ...current,
          status: "uploading",
          progress_percent: 0,
        }));
        activeUploadItemIdRef.current = item.id;
        try {
          const uploaded = await uploadWikiImportSessionItem({
            sessionId: session.id,
            itemId: item.id,
            file: sourceFile,
            onProgress: (progressPercent) => {
              patchImportItem(item.id, (current) => ({
                ...current,
                status: "uploading",
                progress_percent: progressPercent,
              }));
            },
          });
          if (cancelRequestedRef.current) {
            return { sessionId: session.id, status: "cancelled" as const };
          }
          activeUploadItemIdRef.current = null;
          setImportSession(uploaded.session);
          lastSession = uploaded.session;
          replaceImportItem(uploaded.item);
          if (cancelRequestedRef.current) {
            return { sessionId: session.id, status: "cancelled" as const };
          }
          continue;
        } catch (error) {
          const message = messageFromError(error);
          activeUploadItemIdRef.current = null;
          patchImportItem(item.id, (current) => ({
            ...current,
            status: "failed",
            progress_percent: current.progress_percent > 0 ? current.progress_percent : 100,
          }));
          setImportError(message);
          try {
            lastSession = await refreshSession(session.id);
          } catch {
            // keep the existing local summary if the refresh fails
          }
          try {
            items = await refreshItems(session.id);
          } catch {
            // keep the local queue state if the refresh fails
          }
          if (cancelRequestedRef.current) {
            return { sessionId: session.id, status: "cancelled" as const };
          }
          continue;
        }
      }

      return { sessionId: session.id, status: lastSession.status };
    },
    onSuccess: async (result) => {
      activeUploadItemIdRef.current = null;
      if (!result) {
        return;
      }
      if (result.status === "cancelled") {
        cancelRequestedRef.current = false;
        return;
      }
      if (result.status === "completed") {
        await finalizeCompletedSession(result.sessionId);
      }
    },
    onError: (error) => {
      const activeUploadItemId = activeUploadItemIdRef.current;
      activeUploadItemIdRef.current = null;
      if (cancelRequestedRef.current) {
        cancelRequestedRef.current = false;
        return;
      }
      if (activeUploadItemId != null) {
        patchImportItem(activeUploadItemId, (current) => ({
          ...current,
          status: "failed",
          progress_percent: current.progress_percent > 0 ? current.progress_percent : 100,
        }));
      }
      if (importSession != null) {
        void refreshItems(importSession.id).catch(() => undefined);
      }
      setImportError(messageFromError(error));
    },
  });

  async function resolveItem(itemId: number, action: "skip" | "overwrite") {
    if (!importSession) {
      return;
    }
    setImportError("");
    setActionPendingKey(`item:${itemId}:${action}`);
    try {
      const resolved = await resolveWikiImportSessionItem({
        sessionId: importSession.id,
        itemId,
        action,
      });
      setImportSession(resolved.session);
      await refreshItems(importSession.id);
      if (resolved.session.status === "completed") {
        await finalizeCompletedSession(importSession.id);
      }
    } catch (error) {
      setImportError(messageFromError(error));
    } finally {
      setActionPendingKey(null);
    }
  }

  async function bulkResolve(action: "skip_all" | "overwrite_all") {
    if (!importSession) {
      return;
    }
    setImportError("");
    setActionPendingKey(`bulk:${action}`);
    try {
      const resolved = await bulkResolveWikiImportSession({
        sessionId: importSession.id,
        action,
      });
      setImportSession(resolved);
      await refreshItems(importSession.id);
      if (resolved.status === "completed") {
        await finalizeCompletedSession(importSession.id);
      }
    } catch (error) {
      setImportError(messageFromError(error));
    } finally {
      setActionPendingKey(null);
    }
  }

  async function cancelImport() {
    if (!importSession) {
      closeImportDialog();
      return true;
    }
    cancelRequestedRef.current = true;
    setImportError("");
    setActionPendingKey("session:cancel");
    try {
      const cancelled = await cancelWikiImportSession(importSession.id);
      setImportSession(cancelled);
      await refreshItems(importSession.id);
      resetImportState();
      onRouteChange({ drawer: null });
      onBackgroundSessionChange?.(null);
      return true;
    } catch (error) {
      cancelRequestedRef.current = false;
      setImportError(messageFromError(error));
      return false;
    } finally {
      setActionPendingKey(null);
    }
  }

  async function retryItem(itemId: number) {
    if (!importSession) {
      return;
    }
    setImportError("");
    setActionPendingKey(`item:${itemId}:retry`);
    try {
      const retried = await retryWikiImportSessionItem({
        sessionId: importSession.id,
        itemId,
      });
      setImportSession(retried.session);
      await refreshItems(importSession.id);
      if (retried.session.status === "completed") {
        await finalizeCompletedSession(importSession.id);
      }
    } catch (error) {
      setImportError(messageFromError(error));
    } finally {
      setActionPendingKey(null);
    }
  }

  async function retryFailed() {
    if (!importSession) {
      return;
    }
    setImportError("");
    setActionPendingKey("session:retry-failed");
    try {
      const retried = await retryFailedWikiImportSession(importSession.id);
      setImportSession(retried);
      await refreshItems(importSession.id);
      if (retried.status === "completed") {
        await finalizeCompletedSession(importSession.id);
      }
    } catch (error) {
      setImportError(messageFromError(error));
    } finally {
      setActionPendingKey(null);
    }
  }

  return {
    actionPendingKey,
    bulkResolve,
    cancelImport,
    continueImportInBackground,
    hasUnfinishedSession:
      importSession?.status === "running" ||
      (importSessionMutation.isPending && importSession?.status !== "completed") ||
      actionPendingKey === "session:cancel",
    importError,
    importParent,
    importSession,
    importSessionItems,
    openImportDialog,
    closeImportDialog,
    onFilesSelected: (payload: {
      files: File[];
      items: WikiImportSelectionItem[];
      mode: "markdown" | "directory";
    }) => {
      setImportSession(null);
      setImportSessionItems(null);
      setImportError("");
      importSessionMutation.mutate(payload);
    },
    pending: importSessionMutation.isPending,
    resolveItem,
    retryFailed,
    retryItem,
    resetImportState,
    setImportError,
  };
}
