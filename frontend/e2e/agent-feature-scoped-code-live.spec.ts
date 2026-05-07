import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_FEATURE_SCOPED_CODE_E2E === "1";
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
  scopeSources: string[];
};

test.describe.configure({ timeout: 600_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_FEATURE_SCOPED_CODE_E2E=1 to run feature-scoped code live E2E.",
);

test("agent code tools stay inside the model-selected feature repo scope", async ({ page }) => {
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
  await ensureLlmConfig(page);

  const repo = await registerRepo(page, {
    name: `Feature scoped claude-code ${Date.now()}`,
    localPath: repoPath,
  });
  const feature = await createFeature(page, {
    name: `Claude Code 源码 ${Date.now()}`,
    description:
      "Claude Code 源码学习特性，包含 PermissionMode、工具权限、TUI buddy 电子宠物等代码分析问题。",
  });
  await linkFeatureRepo(page, feature.id, repo.id);

  const sessionId = await createSession(page, `Feature scoped live ${Date.now()}`);
  const result = await postMessage(
    page,
    sessionId,
    "Claude Code 的 PermissionMode 在哪里定义或使用？请根据候选特性判断代码范围后查询源码，并给出具体文件路径。不要把问题扩展到其它仓库。",
  );

  expect(result.text.trim()).not.toEqual("");
  expect(result.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(result.toolNames).toContain("search_code");
  expect(result.scopeSources).toContain("feature_scope");
  expect(result.scopeSources).not.toContain("explicit_user_repo");
});

test("agent can use an AnythingLLM feature-linked repo without explicit repo scope", async ({
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

  const repo = await registerRepo(page, {
    name: `Feature scoped anything-llm ${Date.now()}`,
    localPath: repoPath,
  });
  const feature = await createFeature(page, {
    name: `AnythingLLM 源码 ${Date.now()}`,
    description:
      "AnythingLLM 源码学习特性，包含 DataConnectorOption、文档上传、RAG 切分和向量检索处理流程。",
  });
  await linkFeatureRepo(page, feature.id, repo.id);

  const sessionId = await createSession(page, `AnythingLLM feature scoped live ${Date.now()}`);
  const result = await postMessage(
    page,
    sessionId,
    "AnythingLLM 的 DataConnectorOption 在哪里定义或使用？请根据候选特性判断代码范围后查询源码，并给出具体文件路径。",
  );

  expect(result.text.trim()).not.toEqual("");
  expect(result.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(result.toolNames.length).toBeGreaterThan(0);
  expect(result.scopeSources).toContain("feature_scope");
  expect(result.scopeSources).not.toContain("explicit_user_repo");
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
          name: `Live Feature Scope ${Date.now()}`,
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
  return repo;
}

async function createFeature(
  page: import("@playwright/test").Page,
  payload: { name: string; description: string },
) {
  return page.evaluate(async ({ name, description }) => {
    const response = await fetch("/api/features", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    if (!response.ok) {
      throw new Error(`create feature failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as { id: number; name: string };
  }, payload);
}

async function linkFeatureRepo(
  page: import("@playwright/test").Page,
  featureId: number,
  repoId: string,
) {
  await page.evaluate(
    async ({ featureId, repoId }) => {
      const response = await fetch(`/api/features/${featureId}/repos/${repoId}`, {
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`link feature repo failed: ${response.status} ${await response.text()}`);
      }
    },
    { featureId, repoId },
  );
}

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
      const scopeSources: string[] = [];

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
          if (eventType === "tool_result") {
            const scopeSource = data.version_info?.scope_source;
            if (scopeSource) {
              scopeSources.push(String(scopeSource));
            }
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
        if (eventType === "tool_result") {
          const scopeSource = String(data.version_info?.scope_source ?? "");
          if (scopeSource) {
            scopeSources.push(scopeSource);
          }
        }
        if (eventType === "error") {
          throw new Error(`agent error: ${JSON.stringify(data)}`);
        }
      }
      return {
        text,
        toolNames: toolNames.filter(Boolean),
        scopeSources: scopeSources.filter(Boolean),
      };
    },
    { sessionId, content },
  );
}

function referenceRepoPath(relativePath: string) {
  const currentFile = fileURLToPath(import.meta.url);
  return path.resolve(path.dirname(currentFile), "../../references", relativePath);
}
