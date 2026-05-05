import { useQuery } from "@tanstack/react-query";

import { searchWiki } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";

export function useWikiSearch(featureId: number | null, query: string) {
  const normalizedQuery = query.trim();
  return useQuery({
    queryKey: wikiQueryKeys.search(null, featureId, normalizedQuery),
    queryFn: () =>
      searchWiki(normalizedQuery, {
        currentFeatureId: featureId,
      }),
    enabled: featureId != null && normalizedQuery.length > 0,
  });
}
