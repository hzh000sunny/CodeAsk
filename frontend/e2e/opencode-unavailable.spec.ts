import { expect, test } from "@playwright/test";

test("opencode unavailable errors are shown in the centered failure dialog", async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);

    function jsonResponse(value: unknown, init: ResponseInit = {}) {
      return new Response(JSON.stringify(value), {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(init.headers ?? {}),
        },
      });
    }

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), window.location.origin);
      const path = url.pathname;
      const method = (init?.method ?? "GET").toUpperCase();

      if (path === "/api/me") {
        return jsonResponse({
          authenticated: false,
          subject_id: "browser-opencode-unavailable",
          display_name: "browser-opencode-unavailable",
        });
      }
      if (path === "/api/sessions" && method === "GET") {
        return jsonResponse([
          {
            id: "sess_unavailable",
            title: "opencode 不可用测试",
            created_by_subject_id: "browser-opencode-unavailable",
            status: "active",
            pinned: false,
            created_at: "2026-05-16T08:00:00",
            updated_at: "2026-05-16T08:00:00",
          },
        ]);
      }
      if (path === "/api/features" || path === "/api/llm-configs" || path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      if (path === "/api/repos") {
        return jsonResponse({ repos: [] });
      }
      if (path === "/api/analysis-policies") {
        return jsonResponse([]);
      }
      if (
        path === "/api/sessions/sess_unavailable/turns" ||
        path === "/api/sessions/sess_unavailable/traces" ||
        path === "/api/sessions/sess_unavailable/attachments"
      ) {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_unavailable/messages" && method === "POST") {
        return new Response(
          'event: error\ndata: {"backend":"opencode","code":"opencode_bin_missing","error":"opencode executable was not found"}\n\n',
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }
      return originalFetch(input, init);
    };
  });

  await page.goto("/#/sessions?session=sess_unavailable", { waitUntil: "networkidle" });
  await expect(page.getByRole("region", { name: "会话列表" }).getByText("opencode 不可用测试")).toBeVisible();

  await page.getByRole("textbox", { name: "会话输入" }).fill("测试 opencode 不可用");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(
    page.getByText("Agent 运行失败：opencode executable was not found（opencode_bin_missing）"),
  ).toBeVisible();
});
