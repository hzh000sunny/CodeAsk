import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { resetSubjectScopedQueries } from "../src/lib/auth-cache";

describe("resetSubjectScopedQueries", () => {
  it("clears subject-scoped caches and keeps current auth identity", () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(["sessions"], [{ id: "sess_1" }]);
    queryClient.setQueryData(["session-turns", "sess_1"], [{ id: "turn_1" }]);
    queryClient.setQueryData(["feature-admins", 1], [{ username: "alice" }]);
    queryClient.setQueryData(["wiki-tree", { featureId: 1 }], { nodes: [] });
    queryClient.setQueryData(["auth", "me"], { username: "alice" });

    resetSubjectScopedQueries(queryClient);

    expect(queryClient.getQueryData(["sessions"])).toBeUndefined();
    expect(queryClient.getQueryData(["session-turns", "sess_1"])).toBeUndefined();
    expect(queryClient.getQueryData(["feature-admins", 1])).toBeUndefined();
    expect(queryClient.getQueryData(["wiki-tree", { featureId: 1 }])).toBeUndefined();
    expect(queryClient.getQueryData(["auth", "me"])).toEqual({ username: "alice" });
  });
});
