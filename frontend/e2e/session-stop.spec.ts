import { expect, test } from "@playwright/test";

test("stopping an active generation aborts and keeps the truncated visible turn", async ({ page }) => {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    const abortCalls: string[] = [];
    Object.defineProperty(window, "__codeaskAbortCalls", {
      value: abortCalls,
      writable: false,
    });

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
          subject_id: "browser-stop-test",
          display_name: "browser-stop-test",
        });
      }
      if (path === "/api/sessions" && method === "GET") {
        return jsonResponse([
          {
            id: "sess_stop",
            title: "停止生成测试",
            created_by_subject_id: "browser-stop-test",
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
      if (path === "/api/sessions/sess_stop/turns" || path === "/api/sessions/sess_stop/traces") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_stop/attachments") {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_stop/messages" && method === "POST") {
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'event: retrieval_context\ndata: {"feature_candidates":[],"wiki_hits":[],"report_hits":[]}\n\n',
                ),
              );
              controller.enqueue(
                encoder.encode('event: text_delta\ndata: {"text":"正在生成一个很长的回答"}\n\n'),
              );
              init?.signal?.addEventListener("abort", () => {
                controller.error(new DOMException("Aborted", "AbortError"));
              });
            },
          }),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }
      if (/^\/api\/sessions\/sess_stop\/turns\/turn_client_[^/]+\/abort$/.test(path) && method === "POST") {
        abortCalls.push(path);
        return new Response(null, { status: 204 });
      }
      return originalFetch(input, init);
    };
  });

  await page.goto("/#/sessions?session=sess_stop", { waitUntil: "networkidle" });
  await expect(page.getByRole("region", { name: "会话列表" }).getByText("停止生成测试")).toBeVisible();

  await page.getByRole("textbox", { name: "会话输入" }).fill("需要中断的长回答");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("正在生成一个很长的回答")).toBeVisible();
  await expect(page.getByText("上下文已准备")).toBeVisible();

  await page.getByRole("button", { name: "停止", exact: true }).click();

  await expect(page.getByText("需要中断的长回答")).toBeVisible();
  await expect(page.getByText("正在生成一个很长的回答")).toBeVisible();
  await expect(page.getByText("已停止", { exact: true })).toBeVisible();
  await expect(page.getByText("已停止生成")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => (window as unknown as { __codeaskAbortCalls: string[] }).__codeaskAbortCalls.length),
    )
    .toBe(1);
});
