import type { QueryClient } from "@tanstack/react-query";

export function resetSubjectScopedQueries(queryClient: QueryClient) {
  queryClient.removeQueries({ queryKey: ["sessions"] });
  queryClient.removeQueries({ queryKey: ["session-turns"] });
  queryClient.removeQueries({ queryKey: ["session-traces"] });
  queryClient.removeQueries({ queryKey: ["session-attachments"] });
  queryClient.removeQueries({ queryKey: ["user-llm-configs"] });
  queryClient.removeQueries({ queryKey: ["admin-llm-configs"] });
}
