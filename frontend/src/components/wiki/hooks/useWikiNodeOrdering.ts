import { useMutation, type QueryClient } from "@tanstack/react-query";

import { moveWikiNodeWithLegacyFallback } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import type { WikiTreeNodeRecord } from "../../../lib/wiki/tree";
import type { WikiMoveNodePayload } from "../../../types/wiki";
import {
  buildLegacyMoveUpdates,
  buildMoveDownPayload,
  buildMoveUpPayload,
} from "../../../lib/wiki/tree-ordering";
import { messageFromError } from "../../features/feature-utils";

export function useWikiNodeOrdering({
  onError,
  onSuccess,
  queryClient,
  tree,
}: {
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  queryClient: QueryClient;
  tree: WikiTreeNodeRecord[];
}) {
  const moveMutation = useMutation({
    mutationFn: async ({
      nodeId,
      payload,
    }: { nodeId: number; payload: WikiMoveNodePayload }) =>
      moveWikiNodeWithLegacyFallback(
        nodeId,
        payload,
        buildLegacyMoveUpdates(tree, {
          draggedNodeId: nodeId,
          target_parent_id: payload.target_parent_id ?? null,
          target_index: payload.target_index,
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.trees() }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "document"] }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "versions"] }),
      ]);
      onSuccess("Wiki 节点顺序已更新");
    },
    onError: (error) => {
      onError(`排序失败：${messageFromError(error)}`);
    },
  });

  function moveUp(node: WikiTreeNodeRecord) {
    const payload = buildMoveUpPayload(tree, node.id);
    if (!payload) {
      return;
    }
    moveMutation.mutate({ nodeId: node.id, payload });
  }

  function moveDown(node: WikiTreeNodeRecord) {
    const payload = buildMoveDownPayload(tree, node.id);
    if (!payload) {
      return;
    }
    moveMutation.mutate({ nodeId: node.id, payload });
  }

  function moveNode(node: WikiTreeNodeRecord, payload: WikiMoveNodePayload) {
    moveMutation.mutate({ nodeId: node.id, payload });
  }

  return {
    moveDown,
    moveMutation,
    moveNode,
    moveUp,
  };
}
