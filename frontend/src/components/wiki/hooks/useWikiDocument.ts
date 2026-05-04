import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { getWikiDocument, listWikiVersions } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";

export function useWikiDocument(nodeId: number | null, enabled: boolean) {
  const documentQuery = useQuery({
    queryKey: wikiQueryKeys.document(nodeId),
    queryFn: () => getWikiDocument(nodeId as number),
    enabled: enabled && nodeId != null,
  });

  const versionsQuery = useQuery({
    queryKey: wikiQueryKeys.versions(nodeId),
    queryFn: () => listWikiVersions(nodeId as number),
    enabled: enabled && nodeId != null,
  });

  const currentVersion = useMemo(() => {
    const currentId = documentQuery.data?.current_version_id;
    return versionsQuery.data?.versions.find((item) => item.id === currentId) ?? null;
  }, [documentQuery.data?.current_version_id, versionsQuery.data?.versions]);

  return {
    documentQuery,
    versionsQuery,
    currentVersion,
  };
}
