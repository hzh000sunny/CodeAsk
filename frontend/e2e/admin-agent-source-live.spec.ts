import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_AGENT_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const LLM_API_KEY = process.env.CODEASK_LIVE_AGENT_LLM_API_KEY;
const LLM_BASE_URL =
  process.env.CODEASK_LIVE_AGENT_LLM_BASE_URL ??
  "https://ark.cn-beijing.volces.com/api/coding/v3";
const LLM_MODEL = process.env.CODEASK_LIVE_AGENT_LLM_MODEL ?? "GLM-5.1";
const LLM_PROTOCOL = process.env.CODEASK_LIVE_AGENT_LLM_PROTOCOL ?? "openai";

type StreamResult = {
  text: string;
  toolNames: string[];
};

test.describe.configure({ timeout: 300_000 });
test.skip(!ENABLED, "Set CODEASK_RUN_LIVE_AGENT_E2E=1 to run live agent E2E tests.");

test("admin can run a full source-code agent conversation from the frontend", async ({
  page,
}) => {
  const repoPath = referenceRepoPath("claude-code/claude-code");
  test.skip(
    !existsSync(path.join(repoPath, ".git")),
    `reference repo is not a git repository: ${repoPath}`,
  );

  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status}`);
    }
    return (await response.json()) as Array<{ enabled?: boolean }>;
  });
  if (!llmConfigs.some((config) => config.enabled)) {
    test.skip(!LLM_API_KEY, "No enabled LLM config and CODEASK_LIVE_AGENT_LLM_API_KEY is unset.");
    await page.evaluate(
      async ({ apiKey, baseUrl, model, protocol }) => {
        const response = await fetch("/api/admin/llm-configs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: `Live Agent E2E ${Date.now()}`,
            protocol,
            base_url: baseUrl,
            api_key: apiKey,
            model_name: model,
            max_tokens: 512,
            enabled: true,
          }),
        });
        if (!response.ok) {
          throw new Error(`create llm config failed: ${response.status} ${await response.text()}`);
        }
      },
      {
        apiKey: LLM_API_KEY,
        baseUrl: LLM_BASE_URL,
        model: LLM_MODEL,
        protocol: LLM_PROTOCOL,
      },
    );
  }

  await registerRepo(page, {
    name: `Live claude-code ${Date.now()}`,
    localPath: repoPath,
  });

  const sessionId = await createSession(page, `Live claude code explicit repo ${Date.now()}`);
  const result = await postMessage(
    page,
    sessionId,
    "请使用代码工具查看 claude code 仓库，搜索 PermissionMode 在哪里定义或使用，并给出具体文件路径和简短说明。不要凭空回答。",
  );

  expect(result.text).toMatch(/PermissionMode|src\//i);
  expect(result.text).not.toMatch(/max_tokens|BadRequestError|Agent 运行失败|tool loop exceeded/i);
  expect(
    result.toolNames.some((name) =>
      ["list_code_repos", "search_code", "read_code_file"].includes(name),
    ),
  ).toBe(true);

  await page.reload({ waitUntil: "networkidle" });
  expect(sessionId).toMatch(/sess_[a-f0-9]{16}/);
  const persisted = await page.evaluate(async (id) => {
    const turnsResponse = await fetch(`/api/sessions/${id}/turns`);
    if (!turnsResponse.ok) {
      throw new Error(`list turns failed: ${turnsResponse.status}`);
    }
    const tracesResponse = await fetch(`/api/sessions/${id}/traces`);
    if (!tracesResponse.ok) {
      throw new Error(`list traces failed: ${tracesResponse.status}`);
    }
    const turns = (await turnsResponse.json()) as Array<{ role: string; content: string }>;
    const traces = (await tracesResponse.json()) as Array<{
      event_type: string;
      payload?: { tool_name?: string };
    }>;
    return { turns, traces };
  }, sessionId);
  expect(
    persisted.turns.some(
      (turn) => turn.role === "agent" && /PermissionMode|src\//i.test(turn.content),
    ),
  ).toBe(true);
  expect(
    persisted.traces.some((trace) =>
      ["list_code_repos", "search_code", "read_code_file"].includes(
        trace.payload?.tool_name ?? "",
      ),
    ),
  ).toBe(true);
});

async function createSession(page: import("@playwright/test").Page, title: string) {
  return page.evaluate(async (title) => {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  }, title);
}

async function postMessage(
  page: import("@playwright/test").Page,
  sessionId: string,
  content: string,
): Promise<StreamResult> {
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
      const toolNames: string[] = [];

      function readEventFrames(source: string) {
        const frames: string[] = [];
        let remaining = source;
        while (true) {
          const match = remaining.match(/\r?\n\r?\n/);
          if (!match || match.index == null) {
            break;
          }
          const boundary = match.index;
          frames.push(remaining.slice(0, boundary));
          remaining = remaining.slice(boundary + match[0].length);
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
          data:
            dataLines.length > 0
              ? JSON.parse(dataLines.join("\n"))
              : {},
        };
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
          const { eventType, data } = parseFrame(frame);
          if (eventType === "text_delta") {
            text += String(data.delta ?? data.text ?? "");
          }
          if (eventType === "tool_call") {
            toolNames.push(String(data.tool_name ?? ""));
          }
          if (eventType === "error") {
            throw new Error(`agent error: ${JSON.stringify(data)}`);
          }
        }
      }
      buffer += decoder.decode();
      for (const frame of readEventFrames(`${buffer}\n\n`).frames) {
        const { eventType, data } = parseFrame(frame);
        if (eventType === "text_delta") {
          text += String(data.delta ?? data.text ?? "");
        }
        if (eventType === "tool_call") {
          toolNames.push(String(data.tool_name ?? ""));
        }
        if (eventType === "error") {
          throw new Error(`agent error: ${JSON.stringify(data)}`);
        }
      }
      return {
        text,
        toolNames: toolNames.filter(Boolean),
      };
    },
    { sessionId, content },
  );
}

async function registerRepo(
  page: import("@playwright/test").Page,
  payload: { name: string; localPath: string },
) {
  const repo = await page.evaluate(async ({ name, localPath }) => {
    const create = await fetch("/api/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        source: "local_dir",
        local_path: localPath,
      }),
    });
    if (!create.ok) {
      throw new Error(`create repo failed: ${create.status} ${await create.text()}`);
    }
    return (await create.json()) as { id: string };
  }, payload);

  await expect
    .poll(
      async () =>
        page.evaluate(async (repoId) => {
          const response = await fetch(`/api/repos/${repoId}`);
          if (!response.ok) {
            throw new Error(`get repo failed: ${response.status}`);
          }
          return ((await response.json()) as { status: string }).status;
        }, repo.id),
      { timeout: 120_000 },
    )
    .toBe("ready");
}

function referenceRepoPath(relativePath: string) {
  const currentFile = fileURLToPath(import.meta.url);
  return path.resolve(path.dirname(currentFile), "../../references", relativePath);
}
