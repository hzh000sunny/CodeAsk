import type { WikiDocumentResolvedRef } from "../../types/wiki";

export interface WikiMarkdownLinkMaps {
  imageSrcMap: Record<string, string>;
  linkHrefMap: Record<string, string>;
}

export function buildWikiMarkdownLinkMaps(
  refs: WikiDocumentResolvedRef[],
  featureId: number | null,
): WikiMarkdownLinkMaps {
  const imageSrcMap: Record<string, string> = {};
  const linkHrefMap: Record<string, string> = {};
  for (const ref of refs) {
    if (ref.broken || ref.resolved_node_id == null) {
      continue;
    }
    if (ref.kind === "image") {
      imageSrcMap[ref.target] = `/api/wiki/assets/${ref.resolved_node_id}/content`;
      continue;
    }
    if (featureId != null) {
      linkHrefMap[ref.target] = wikiDocumentHref(featureId, ref.resolved_node_id);
    }
  }
  return { imageSrcMap, linkHrefMap };
}

export function wikiDocumentHref(featureId: number, nodeId: number) {
  return `#/wiki?feature=${featureId}&node=${nodeId}`;
}
