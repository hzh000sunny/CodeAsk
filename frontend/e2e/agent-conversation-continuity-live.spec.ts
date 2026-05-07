import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_AGENT_CONTINUITY_E2E === "1";
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
  eventTypes: string[];
};

test.describe.configure({ timeout: 600_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_AGENT_CONTINUITY_E2E=1 to run live conversation continuity E2E.",
);

test("agent can answer a follow-up about previous tool actions in the same session", async ({
  page,
}) => {
  const repoPath = referenceRepoPath("anything-llm");
  test.skip(
    !existsSync(path.join(repoPath, ".git")),
    `reference repo is not a git repository: ${repoPath}`,
  );

  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
  await ensureLlmConfig(page);

  await registerRepo(page, {
    name: `Live continuity anything-llm ${Date.now()}`,
    localPath: repoPath,
  });

  const sessionId = await page.evaluate(async () => {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: `Continuity live ${Date.now()}` }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  });

  const first = await postMessage(
    page,
    sessionId,
    "请使用代码工具在 anything-llm 仓库中搜索 processSingleFile，回答它和 RAG 上传资料处理有什么关系。只需要列出仓库、搜索代码、读取一个最相关源码文件即可，不要继续扩展。",
  );
  expect(first.text.trim()).not.toEqual("");
  expect(first.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(first.toolNames.length, `first turn should use code tools: ${JSON.stringify(first)}`)
    .toBeGreaterThan(0);

  const second = await postMessage(
    page,
    sessionId,
    "你刚刚的回答，有查询代码吗？如果有，请区分是列出仓库、搜索代码还是读取源码文件。",
  );
  expect(second.text.trim()).not.toEqual("");
  expect(second.text).not.toMatch(/第一次交流|无法跨对话|没有给出过回答|无法确认当时/i);
  expect(second.text).toMatch(/代码|工具|仓库|搜索|读取|源码|list_code_repos|search_code|read_code_file/i);

  const turns = await page.evaluate(async (id) => {
    const response = await fetch(`/api/sessions/${id}/turns`);
    if (!response.ok) {
      throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{ role: string; content: string }>;
  }, sessionId);
  expect(turns.filter((turn) => turn.role === "user")).toHaveLength(2);
  expect(turns.filter((turn) => turn.role === "agent")).toHaveLength(2);

  await page.goto(`/#/sessions`, { waitUntil: "networkidle" });
  await page.reload({ waitUntil: "networkidle" });
  const third = await postMessage(page, sessionId, "刷新后继续追问：你上一轮说了什么？");
  expect(third.text.trim()).not.toEqual("");
  expect(third.text).not.toMatch(/第一次交流|无法跨对话|没有给出过回答/i);
});

async function ensureLlmConfig(page: import("@playwright/test").Page) {
  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status}`);
    }
    return (await response.json()) as Array<{ enabled?: boolean }>;
  });
  if (llmConfigs.some((config) => config.enabled)) {
    return;
  }
  test.skip(!LLM_API_KEY, "No enabled LLM config and CODEASK_LIVE_AGENT_LLM_API_KEY is unset.");
  await page.evaluate(
    async ({ apiKey, baseUrl, model, protocol }) => {
      const response = await fetch("/api/admin/llm-configs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `Live Continuity ${Date.now()}`,
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
      const eventTypes: string[] = [];

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
          if (eventType) {
            eventTypes.push(eventType);
          }
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
        if (eventType) {
          eventTypes.push(eventType);
        }
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
      return { text, toolNames: toolNames.filter(Boolean), eventTypes };
    },
    { sessionId, content },
  );
}

function referenceRepoPath(relativePath: string) {
  const currentFile = fileURLToPath(import.meta.url);
  return path.resolve(path.dirname(currentFile), "../../references", relativePath);
}
