import { useMutation, type QueryClient } from "@tanstack/react-query";

import { reindexWikiNode } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import type { WikiMaintenanceReindexRead } from "../../../types/wiki";
import { messageFromError } from "../../features/feature-utils";

export function useWikiMaintenance({
  onError,
  onSuccess,
  queryClient,
}: {
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  queryClient: QueryClient;
}) {
  const reindexMutation = useMutation({
    mutationFn: async (nodeId: number) => reindexWikiNode(nodeId),
    onSuccess: async (result: WikiMaintenanceReindexRead) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: wikiQueryKeys.trees() }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "document"] }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "versions"] }),
        queryClient.invalidateQueries({ queryKey: [...wikiQueryKeys.all, "search"] }),
      ]);
      onSuccess(`已重新索引 ${result.reindexed_documents} 篇文档`);
    },
    onError: (error) => {
      onError(`重新索引失败：${messageFromError(error)}`);
    },
  });

  return {
    reindexMutation,
  };
}
