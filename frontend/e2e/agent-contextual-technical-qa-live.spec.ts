import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_CONTEXTUAL_TECH_QA_E2E === "1";
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

type ScenarioStep = {
  id: string;
  question: string;
  expectedText: RegExp;
  preferredBehavior: "topic_answer" | "contextual_direct_answer" | "source_investigation";
  codeToolsExpected?: boolean;
};

const CODE_TOOLS = new Set([
  "list_code_repos",
  "search_code",
  "inspect_repo_tree",
  "list_code_paths",
  "read_code_file",
]);

const SCENARIO: ScenarioStep[] = [
  {
    id: "anythingllm_recall_overview",
    question:
      "我们继续围绕 AnythingLLM 这个特性聊。anything llm 是如何处理召回的？先给我一个整体说明。",
    expectedText: /召回|检索|向量|embedding|chunk|workspace|上下文|RAG/i,
    preferredBehavior: "topic_answer",
  },
  {
    id: "inserted_lancedb_sqlite_concept",
    question: "lancedb 和 sqlitedb 有什么区别？",
    expectedText: /LanceDB|向量|embedding|SQLite|关系|SQL|嵌入式/i,
    preferredBehavior: "contextual_direct_answer",
  },
  {
    id: "contextualize_storage_roles",
    question: "那放回刚才的 AnythingLLM / RAG 语境里，它们通常分别适合承担什么角色？",
    expectedText: /向量|检索|embedding|元数据|关系|SQLite|LanceDB/i,
    preferredBehavior: "contextual_direct_answer",
  },
  {
    id: "explicit_source_investigation",
    question:
      "如果要确认 AnythingLLM 源码里具体有没有使用 sqlite 或 better-sqlite3，现在可以根据这个特性关联的仓库查一下代码，给出具体文件路径。",
    expectedText: /sqlite|better-sqlite3|prisma|schema|\.prisma|server\/prisma|文件|路径/i,
    preferredBehavior: "source_investigation",
    codeToolsExpected: true,
  },
];

test.describe.configure({ timeout: 900_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_CONTEXTUAL_TECH_QA_E2E=1 to run contextual technical Q&A live E2E.",
);

test("agent keeps feature context while answering inserted technical questions directly", async ({
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
    name: `Contextual QA anything-llm ${Date.now()}`,
    localPath: repoPath,
  });
  const feature = await createFeature(page, {
    name: `AnythingLLM 场景问答 ${Date.now()}`,
    description:
      "AnythingLLM 特性上下文，包含 RAG 召回、workspace、embedding、LanceDB、SQLite、better-sqlite3、Prisma schema 和源码确认问题。",
  });
  await linkFeatureRepo(page, feature.id, repo.id);

  const sessionId = await createSession(page, `Contextual technical QA live ${Date.now()}`);
  const deviations: Array<{ id: string; reason: string; tools: string[] }> = [];

  for (const step of SCENARIO) {
    const result = await postMessage(page, sessionId, step.question);
    const uniqueTools = Array.from(new Set(result.toolNames));
    const codeTools = uniqueTools.filter((tool) => CODE_TOOLS.has(tool));

    expect(result.text.trim(), step.id).not.toEqual("");
    expect(result.text, step.id).not.toMatch(
      /BadRequestError|Agent 运行失败|max_tokens|Input length|tool loop exceeded/i,
    );
    expect(result.text, step.id).not.toMatch(
      /请.*指定.*仓库|没有配置.*源码仓库|当前没有配置.*仓库|第一次交流|无法跨对话/i,
    );
    expect(result.text, step.id).toMatch(step.expectedText);

    if (step.codeToolsExpected) {
      expect(
        codeTools.length,
        `${step.id} should use code tools; actual tools=${JSON.stringify(uniqueTools)}`,
      ).toBeGreaterThan(0);
      continue;
    }

    if (codeTools.length > 0) {
      deviations.push({
        id: step.id,
        reason: "code tool was used for a topic/contextual concept question",
        tools: codeTools,
      });
    }
  }

  expect(
    deviations.length,
    `too many contextual technical Q&A tool deviations: ${JSON.stringify(deviations, null, 2)}`,
  ).toBeLessThanOrEqual(1);

  const turns = await page.evaluate(async (id) => {
    const response = await fetch(`/api/sessions/${id}/turns`);
    if (!response.ok) {
      throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{ role: string; content: string }>;
  }, sessionId);
  expect(turns.filter((turn) => turn.role === "user")).toHaveLength(SCENARIO.length);
  expect(turns.filter((turn) => turn.role === "agent")).toHaveLength(SCENARIO.length);
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
          name: `Live Contextual QA ${Date.now()}`,
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
      return { text, toolNames: toolNames.filter(Boolean) };
    },
    { sessionId, content },
  );
}

function referenceRepoPath(relativePath: string) {
  const currentFile = fileURLToPath(import.meta.url);
  return path.resolve(path.dirname(currentFile), "../../references", relativePath);
}
