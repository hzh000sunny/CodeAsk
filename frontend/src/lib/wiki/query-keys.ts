export const wikiQueryKeys = {
  all: ["wiki"] as const,
  trees: () => [...wikiQueryKeys.all, "trees"] as const,
  tree: (featureId: number | null) => [...wikiQueryKeys.trees(), featureId] as const,
  node: (nodeId: number | null) => [...wikiQueryKeys.all, "node", nodeId] as const,
  document: (nodeId: number | null) => [...wikiQueryKeys.all, "document", nodeId] as const,
  versions: (nodeId: number | null) => [...wikiQueryKeys.all, "versions", nodeId] as const,
  reportProjections: (featureId: number | null) =>
    [...wikiQueryKeys.all, "report-projections", featureId] as const,
  report: (nodeId: number | null) => [...wikiQueryKeys.all, "report", nodeId] as const,
  search: (featureId: number | null, query: string) =>
    [...wikiQueryKeys.all, "search", featureId, query] as const,
  importJob: (jobId: number | null) => [...wikiQueryKeys.all, "import-job", jobId] as const,
  importItems: (jobId: number | null) => [...wikiQueryKeys.all, "import-items", jobId] as const,
};
