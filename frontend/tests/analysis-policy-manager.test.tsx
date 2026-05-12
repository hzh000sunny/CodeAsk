import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisPolicyManager } from "../src/components/policies/AnalysisPolicyManager";

function renderManager() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AnalysisPolicyManager
        featureId={9}
        scope="feature"
        title="特性分析策略"
      />
    </QueryClientProvider>,
  );
}

describe("AnalysisPolicyManager", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("shows a load failure instead of pretending policies are empty", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("backend unavailable", { status: 500 })),
    );

    renderManager();

    expect(
      await screen.findByText(/加载分析策略失败：backend unavailable/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.queryByText("暂无分析策略")).not.toBeInTheDocument();
  });
});
