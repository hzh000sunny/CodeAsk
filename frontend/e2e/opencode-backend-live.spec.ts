import { expect, test } from "@playwright/test";
import { existsSync, lstatSync, readFileSync } from "node:fs";
import path from "node:path";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENCODE_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const REAL_DATA_DIR = process.env.CODEASK_REAL_DATA_DIR ?? "/home/hzh/.codeask";

test.describe.configure({ timeout: 300_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENCODE_E2E=1 to run the live opencode backend smoke.",
);

test("frontend session sends one turn through opencode backend", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{
      enabled?: boolean;
      model_name?: string;
      protocol?: string;
    }>;
  });
  const enabledConfigs = llmConfigs.filter((config) => config.enabled);
  test.skip(enabledConfigs.length === 0, "No enabled real LLM config is available in CodeAsk.");
  const enabledModelNames = new Set(enabledConfigs.map((config) => config.model_name));

  const sessionTitle = `OpenCode live smoke ${Date.now()}`;
  const sessionId = await page.evaluate(async (title) => {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  }, sessionTitle);

  const stream = await postMessage(
    page,
    sessionId,
    "请用一句话回答：Python list 和 tuple 的核心区别是什么？",
  );
  expect(stream.text.trim()).not.toEqual("");
  expect(stream.eventTypes).toContain("runtime_state");
  expect(stream.eventTypes).toContain("done");

  await expect
    .poll(
      async () =>
        page.evaluate(async (id) => {
          const response = await fetch(`/api/sessions/${id}/turns`);
          if (!response.ok) {
            throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
          }
          return (await response.json()) as Array<{ role: string; content: string }>;
        }, sessionId),
      { timeout: 180_000 },
    )
    .toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: "user" }),
        expect.objectContaining({ role: "agent" }),
      ]),
    );

  await page.goto(`/#/sessions?session=${sessionId}`, { waitUntil: "networkidle" });
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByRole("region", { name: "Agent 行动轨迹" })).toBeVisible();
  await expect(page.getByRole("region", { name: "会话数据" })).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "会话消息" })
      .getByText(/list|tuple|列表|元组/i)
      .last(),
  ).toBeVisible();

  const followUp = await postMessage(
    page,
    sessionId,
    "我刚刚问的问题和 list、tuple 有关吗？请只回答一句话。",
  );
  expect(followUp.text.trim()).not.toEqual("");
  expect(followUp.eventTypes).toContain("done");

  const traces = await page.evaluate(async (id) => {
    const response = await fetch(`/api/sessions/${id}/traces`);
    if (!response.ok) {
      throw new Error(`list traces failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{
      event_type: string;
      payload: Record<string, unknown>;
    }>;
  }, sessionId);
  expect(traces.some((trace) => trace.event_type === "runtime_state")).toBe(true);
  expect(
    traces.some(
      (trace) =>
        trace.event_type === "runtime_state" &&
        trace.payload.backend === "opencode" &&
        enabledModelNames.has(String(trace.payload.model_name)),
    ),
  ).toBe(true);
  const doneTrace = [...traces].reverse().find((trace) => trace.event_type === "done");
  expect(doneTrace?.payload.timing).toMatchObject({
    response_observed: true,
  });

  const sessionDir = path.join(
    REAL_DATA_DIR,
    "agent_sessions",
    "opencode",
    "sessions",
    sessionId,
  );
  const workspaceDir = path.join(sessionDir, "workspace");
  const wikiLink = path.join(workspaceDir, "wiki");
  expect(existsSync(path.join(workspaceDir, "opencode.json"))).toBe(true);
  expect(lstatSync(wikiLink).isSymbolicLink()).toBe(true);
  const config = JSON.parse(readFileSync(path.join(workspaceDir, "opencode.json"), "utf-8"));
  expect(config.permission.bash).toBe("deny");
  expect(config.mcp.codeask.headers["X-CodeAsk-Session"]).toBe(sessionId);

  await expect
    .poll(
      async () =>
        page.evaluate(async (id) => {
          const response = await fetch(`/api/sessions/${id}/turns`);
          if (!response.ok) {
            throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
          }
          return ((await response.json()) as Array<{ role: string }>).map((turn) => turn.role);
        }, sessionId),
      { timeout: 180_000 },
    )
    .toEqual(["user", "agent", "user", "agent"]);
});

test("frontend sends concurrent new sessions through opencode backend", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{
      enabled?: boolean;
      model_name?: string;
    }>;
  });
  const enabledConfigs = llmConfigs.filter((config) => config.enabled);
  test.skip(enabledConfigs.length === 0, "No enabled real LLM config is available in CodeAsk.");
  const enabledModelNames = new Set(enabledConfigs.map((config) => config.model_name));

  const sessionIds = await page.evaluate(async () => {
    const now = Date.now();
    return Promise.all(
      [0, 1, 2].map(async (index) => {
        const response = await fetch("/api/sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: `OpenCode concurrent live ${now}-${index}` }),
        });
        if (!response.ok) {
          throw new Error(`create session failed: ${response.status} ${await response.text()}`);
        }
        return ((await response.json()) as { id: string }).id;
      }),
    );
  });

  const results = await Promise.all(
    sessionIds.map((sessionId, index) =>
      postMessage(
        page,
        sessionId,
        `并发验证 ${index + 1}：请用一句话回答，HTTP 和 HTTPS 的核心区别是什么？`,
      ),
    ),
  );

  for (const result of results) {
    expect(result.text.trim()).not.toEqual("");
    expect(result.eventTypes).toContain("runtime_state");
    expect(result.eventTypes).toContain("done");
    expect(result.eventTypes).not.toContain("error");
  }

  for (const sessionId of sessionIds) {
    await expect
      .poll(
        async () =>
          page.evaluate(async (id) => {
            const response = await fetch(`/api/sessions/${id}/turns`);
            if (!response.ok) {
              throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
            }
            return ((await response.json()) as Array<{ role: string }>).map((turn) => turn.role);
          }, sessionId),
        { timeout: 180_000 },
      )
      .toEqual(["user", "agent"]);

    const traces = await page.evaluate(async (id) => {
      const response = await fetch(`/api/sessions/${id}/traces`);
      if (!response.ok) {
        throw new Error(`list traces failed: ${response.status} ${await response.text()}`);
      }
      return (await response.json()) as Array<{
        event_type: string;
        payload: Record<string, unknown>;
      }>;
    }, sessionId);
    expect(
      traces.some(
        (trace) =>
          trace.event_type === "runtime_state" &&
          trace.payload.backend === "opencode" &&
          enabledModelNames.has(String(trace.payload.model_name)),
      ),
    ).toBe(true);
    expect(traces.some((trace) => trace.event_type === "error")).toBe(false);
  }
});

async function postMessage(
  page: import("@playwright/test").Page,
  sessionId: string,
  content: string,
) {
  return page.evaluate(
    async ({ sessionId, content }) => {
      const response = await fetch(`/api/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!response.ok || !response.body) {
        throw new Error(`post message failed: ${response.status} ${await response.text()}`);
      }
      const decoder = new TextDecoder();
      const reader = response.body.getReader();
      let buffer = "";
      let text = "";
      const eventTypes: string[] = [];

      function readEventFrames(source: string) {
        const frames: string[] = [];
        let remaining = source;
        while (true) {
          const match = remaining.match(/\r?\n\r?\n/);
          if (!match || match.index == null) {
            break;
          }
          frames.push(remaining.slice(0, match.index));
          remaining = remaining.slice(match.index + match[0].length);
        }
        return { frames, remaining };
      }

      function parseFrame(frame: string) {
        let eventType = "";
        const dataLines: string[] = [];
        for (const rawLine of frame.split(/\r?\n/)) {
          if (rawLine.startsWith("event:")) {
            eventType = rawLine.slice("event:".length).trim();
          } else if (rawLine.startsWith("data:")) {
            dataLines.push(rawLine.slice("data:".length).trimStart());
          }
        }
        return {
          eventType,
          data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {},
        };
      }

      function handleFrame(frame: string) {
        const { eventType, data } = parseFrame(frame);
        if (!eventType) {
          return;
        }
        eventTypes.push(eventType);
        if (eventType === "text_delta") {
          text += String(data.delta ?? data.text ?? "");
        }
        if (eventType === "error") {
          throw new Error(`agent error: ${JSON.stringify(data)}`);
        }
      }

      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const parsed = readEventFrames(buffer);
        buffer = parsed.remaining;
        for (const frame of parsed.frames) {
          handleFrame(frame);
        }
      }
      buffer += decoder.decode();
      for (const frame of readEventFrames(`${buffer}\n\n`).frames) {
        handleFrame(frame);
      }
      return { eventTypes, text };
    },
    { sessionId, content },
  );
}
