import { useMutation, type QueryClient } from "@tanstack/react-query";

import { restoreWikiNode, restoreWikiSpace } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import type { WikiNodeRead, WikiSpaceRead } from "../../../types/wiki";
import { messageFromError } from "../../features/feature-utils";

export function useWikiRestoreActions({
  onError,
  onSuccess,
  queryClient,
}: {
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  queryClient: QueryClient;
}) {
  const restoreNodeMutation = useMutation({
    mutationFn: async (nodeId: number) => restoreWikiNode(nodeId),
    onSuccess: async (node: WikiNodeRead) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.trees() }),
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.document(node.id) }),
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.versions(node.id) }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "search"] }),
      ]);
      onSuccess("Wiki 节点已恢复");
    },
    onError: (error) => {
      onError(`恢复节点失败：${messageFromError(error)}`);
    },
  });

  const restoreSpaceMutation = useMutation({
    mutationFn: async (spaceId: number) => restoreWikiSpace(spaceId),
    onSuccess: async (space: WikiSpaceRead) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.trees() }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "space", space.feature_id] }),
        queryClient.invalidateQueries({ queryKey: ["features"] }),
      ]);
      onSuccess("历史特性已恢复");
    },
    onError: (error) => {
      onError(`恢复历史特性失败：${messageFromError(error)}`);
    },
  });

  return {
    restoreNodeMutation,
    restoreSpaceMutation,
  };
}
