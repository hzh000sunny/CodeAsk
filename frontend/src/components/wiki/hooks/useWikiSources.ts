import { useMutation, useQuery, type QueryClient } from "@tanstack/react-query";

import {
  createWikiSource,
  listWikiSources,
  syncWikiSource,
  updateWikiSource,
} from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import type {
  WikiSourceCreatePayload,
  WikiSourceRead,
  WikiSourceUpdatePayload,
} from "../../../types/wiki";
import { messageFromError } from "../../features/feature-utils";

function mergeUpdatedSource(items: WikiSourceRead[] | undefined, next: WikiSourceRead) {
  if (!items) {
    return [next];
  }
  const exists = items.some((item) => item.id === next.id);
  if (!exists) {
    return [...items, next].sort((left, right) => left.id - right.id);
  }
  return items.map((item) => (item.id === next.id ? next : item));
}

export function useWikiSources({
  enabled = true,
  onError,
  onSuccess,
  queryClient,
  spaceId,
}: {
  enabled?: boolean;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
  queryClient: QueryClient;
  spaceId: number | null;
}) {
  const sourcesQuery = useQuery({
    queryKey: wikiQueryKeys.sources(spaceId),
    queryFn: async () => (await listWikiSources(spaceId as number)).items,
    enabled: enabled && spaceId != null,
  });

  const createMutation = useMutation({
    mutationFn: async (payload: Omit<WikiSourceCreatePayload, "space_id">) =>
      createWikiSource({ ...payload, space_id: spaceId as number }),
    onSuccess: async (source) => {
      queryClient.setQueryData<WikiSourceRead[] | undefined>(
        wikiQueryKeys.sources(spaceId),
        (items) => mergeUpdatedSource(items, source),
      );
      await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.sources(spaceId) });
      onSuccess("来源已创建");
    },
    onError: (error) => {
      onError(`创建来源失败：${messageFromError(error)}`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({
      sourceId,
      payload,
    }: {
      sourceId: number;
      payload: WikiSourceUpdatePayload;
    }) => updateWikiSource(sourceId, payload),
    onSuccess: async (source) => {
      queryClient.setQueryData<WikiSourceRead[] | undefined>(
        wikiQueryKeys.sources(spaceId),
        (items) => mergeUpdatedSource(items, source),
      );
      await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.sources(spaceId) });
      onSuccess("来源已更新");
    },
    onError: (error) => {
      onError(`更新来源失败：${messageFromError(error)}`);
    },
  });

  const syncMutation = useMutation({
    mutationFn: async (sourceId: number) => syncWikiSource(sourceId),
    onSuccess: async (source) => {
      queryClient.setQueryData<WikiSourceRead[] | undefined>(
        wikiQueryKeys.sources(spaceId),
        (items) => mergeUpdatedSource(items, source),
      );
      await queryClient.invalidateQueries({ queryKey: wikiQueryKeys.sources(spaceId) });
      onSuccess("来源同步成功");
    },
    onError: (error) => {
      onError(`同步来源失败：${messageFromError(error)}`);
    },
  });

  return {
    createMutation,
    sources: sourcesQuery.data ?? [],
    sourcesQuery,
    syncMutation,
    updateMutation,
  };
}
