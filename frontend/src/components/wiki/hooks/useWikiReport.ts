import { useQuery } from "@tanstack/react-query";

import { getWikiReportByNode, listWikiReportProjections } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";

export function useWikiReportProjections(featureId: number | null) {
  return useQuery({
    queryKey: wikiQueryKeys.reportProjections(featureId),
    queryFn: () => listWikiReportProjections(featureId as number),
    enabled: featureId != null,
  });
}

export function useWikiReport(nodeId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: wikiQueryKeys.report(nodeId),
    queryFn: () => getWikiReportByNode(nodeId as number),
    enabled: enabled && nodeId != null,
  });
}
