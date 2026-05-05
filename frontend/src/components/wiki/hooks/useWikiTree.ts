import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { getWikiTree } from "../../../lib/wiki/api";
import { wikiQueryKeys } from "../../../lib/wiki/query-keys";
import {
  buildWikiTree,
  findFirstReadableDocument,
  findNodeById,
  type WikiTreeNodeRecord,
} from "../../../lib/wiki/tree";

export function useWikiTree(featureId: number | null, nodeId: number | null) {
  const query = useQuery({
    queryKey: wikiQueryKeys.tree(featureId),
    queryFn: () => getWikiTree(featureId),
  });

  const tree = useMemo<WikiTreeNodeRecord[]>(
    () => buildWikiTree(query.data?.nodes ?? []),
    [query.data?.nodes],
  );
  const firstDocument = useMemo(() => findFirstReadableDocument(tree), [tree]);
  const selectedNode = useMemo(() => findNodeById(tree, nodeId), [nodeId, tree]);

  return {
    ...query,
    tree,
    space: query.data?.space ?? null,
    firstDocument,
    selectedNode,
  };
}
