import { expect, test } from "@playwright/test";

test("opencode denied Bash/Edit/Write events remain visible in the action trace", async ({
  page,
}) => {
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

      if (path === "/api/me" || path === "/api/auth/me") {
        return jsonResponse({
          authenticated: true,
          display_name: "Admin",
          role: "admin",
          subject_id: "admin",
        });
      }
      if (path === "/api/sessions" && method === "GET") {
        return jsonResponse([
          {
            created_at: "2026-05-16T08:00:00",
            created_by_subject_id: "admin",
            id: "sess_denied",
            pinned: false,
            status: "active",
            title: "opencode 权限测试",
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
        path === "/api/sessions/sess_denied/turns" ||
        path === "/api/sessions/sess_denied/traces" ||
        path === "/api/sessions/sess_denied/attachments"
      ) {
        return jsonResponse([]);
      }
      if (path === "/api/sessions/sess_denied/messages" && method === "POST") {
        return new Response(
          [
            'event: tool_call\ndata: {"tool_name":"Bash","tool_call_id":"call_bash_1","arguments_summary":{"command":"pwd"}}',
            'event: tool_result\ndata: {"tool_name":"Bash","tool_call_id":"call_bash_1","ok":false,"result":{"ok":false,"message":"Bash is disabled by CodeAsk opencode permissions"},"error_type":"permission_denied"}',
            'event: tool_call\ndata: {"tool_name":"Edit","tool_call_id":"call_edit_1","arguments_summary":{"path":"README.md"}}',
            'event: tool_result\ndata: {"tool_name":"Edit","tool_call_id":"call_edit_1","ok":false,"result":{"ok":false,"message":"Edit is disabled by CodeAsk opencode permissions"},"error_type":"permission_denied"}',
            'event: tool_call\ndata: {"tool_name":"Write","tool_call_id":"call_write_1","arguments_summary":{"path":"tmp.txt"}}',
            'event: tool_result\ndata: {"tool_name":"Write","tool_call_id":"call_write_1","ok":false,"result":{"ok":false,"message":"Write is disabled by CodeAsk opencode permissions"},"error_type":"permission_denied"}',
            'event: text_delta\ndata: {"text":"权限边界已生效。"}',
            'event: done\ndata: {"turn_id":"turn_denied"}',
            "",
          ].join("\n\n"),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }
      return originalFetch(input, init);
    };
  });

  await page.goto("/#/sessions?session=sess_denied", { waitUntil: "networkidle" });
  await expect(
    page.getByRole("heading", { name: "opencode 权限测试" }),
  ).toBeVisible();

  await page.getByRole("textbox", { name: "会话输入" }).fill("尝试执行受限工具");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("权限边界已生效。")).toBeVisible();
  await expect(page.getByRole("button", { name: /Bash失败/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Edit失败/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Write失败/ })).toBeVisible();
  await expect(page.getByText(/错误：permission_denied/).first()).toBeVisible();
});
