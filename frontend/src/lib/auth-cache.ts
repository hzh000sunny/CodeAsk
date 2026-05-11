import type { QueryClient } from "@tanstack/react-query";

export function resetSubjectScopedQueries(queryClient: QueryClient) {
  const keys = [
    ["sessions"],
    ["session-turns"],
    ["session-traces"],
    ["session-attachments"],
    ["users"],
    ["feature-admins"],
    ["wiki"],
    ["wiki-tree"],
    ["wiki-document"],
    ["wiki-documents"],
    ["user-llm-configs"],
    ["admin-llm-configs"],
  ];
  keys.forEach((queryKey) => queryClient.removeQueries({ queryKey }));
}
