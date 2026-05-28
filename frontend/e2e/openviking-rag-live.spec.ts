import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_OPENVIKING_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const ANON_SUBJECT_ID = `anonymous@openviking-e2e-${Date.now()}`;

type StreamResult = {
  text: string;
  toolNames: string[];
  toolResultTexts: string[];
};

const REPOSITORY_TOOLS = new Set([
  "codeask_prepare_worktree",
  "list_code_repos",
  "search_code",
  "inspect_repo_tree",
  "list_code_paths",
  "read_code_file",
]);
const FILE_INSPECTION_TOOLS = new Set(["glob", "grep", "read"]);

test.describe.configure({ timeout: 600_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_OPENVIKING_E2E=1 to run live OpenViking RAG E2E.",
);

test.beforeEach(async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
  await ensureOpenVikingHealthy(page);
  await ensureEnabledLlmConfig(page);
});

test("session can use OpenViking semantic recall for synced wiki knowledge", async ({
  page,
}) => {
  const marker = `rag-wiki-smoke-${Date.now()}`;
  const uri =
    `viking://resources/codeask/features/openviking-rag-live/knowledge-base/${marker}.md`;
  await enqueueAndIndexManualResource(page, {
    content:
      `# ${marker}\n\n` +
      `RAG smoke marker ${marker} means CodeAsk can retrieve published wiki ` +
      "knowledge through OpenViking semantic search and cite the viking URI.",
    featureSlug: "openviking-rag-live",
    filename: `${marker}.md`,
    sourceId: marker,
    sourceType: "wiki_doc",
    vikingUri: uri,
  });

  await logout(page);
  const sessionId = await createSession(page, `OpenViking RAG wiki ${marker}`);
  const result = await postMessage(
    page,
    sessionId,
    `${marker} 是什么？请根据你能看到的 CodeAsk 知识回答，并说明来源。`,
  );

  expect(result.text.trim()).not.toEqual("");
  expect(result.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(result.text).toMatch(new RegExp(escapeRegExp(marker), "i"));
  expect(result.toolNames).not.toContain("openviking_remember");
  expect(result.toolNames).not.toContain("openviking_add_resource");
  expect(result.toolNames).not.toContain("openviking_forget");
  attachToolSample("wiki-recall", result);
});

test("source-code question can bridge from OpenViking recall to prepared worktree", async ({
  page,
}) => {
  const repoPath = referenceRepoPath("claude-code/claude-code");
  test.skip(
    !existsSync(repoPath),
    `reference repo directory does not exist: ${repoPath}`,
  );

  const marker = `rag-code-bridge-${Date.now()}`;
  const repo = await registerRepo(page, {
    localPath: repoPath,
    name: `OpenViking claude-code ${Date.now()}`,
  });
  await waitForRepoReady(page, repo.id);
  const uri = `viking://resources/codeask/features/openviking-rag-live/knowledge-base/${marker}.md`;
  await enqueueAndIndexManualResource(page, {
    content:
      `# ${marker}\n\n` +
      `This verified OpenViking-only clue maps marker ${marker} to CodeAsk ` +
      `repository "${repo.name}" with repo_id "${repo.id}". ` +
      "For Claude Code PermissionMode questions, prepare that repository worktree " +
      "and read the real source files for evidence.",
    featureSlug: "openviking-rag-live",
    filename: `${marker}.md`,
    sourceId: marker,
    sourceType: "wiki_doc",
    vikingUri: uri,
  });

  await logout(page);
  const sessionId = await createSession(page, `OpenViking RAG code ${marker}`);
  const result = await postMessage(
    page,
    sessionId,
    `Claude Code 的 PermissionMode 在源码哪里定义或使用？这个问题和 ${marker} 相关。`,
  );

  expect(result.text.trim()).not.toEqual("");
  expect(result.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(result.text).toMatch(/PermissionMode|src\/|\.ts|\.tsx|permission/i);
  attachToolSample("source-bridge", result);
});

test("session falls back to workspace wiki search when OpenViking is unavailable", async ({
  page,
}) => {
  const marker = `rag-degraded-${Date.now()}`;
  const feature = await createFeature(page, {
    description: `OpenViking degraded fallback fixture ${marker}.`,
    name: `OpenViking Degraded Fallback ${Date.now()}`,
  });
  await uploadLegacyMarkdownDocument(page, {
    body:
      `# ${marker}\n\n` +
      `Degraded fallback marker ${marker} proves CodeAsk can answer from ` +
      "workspace wiki files when OpenViking is temporarily unavailable.",
    featureId: feature.id,
    filename: `${marker}.md`,
  });
  await stopOpenVikingUntilDegraded(page);

  await logout(page);
  const sessionId = await createSession(page, `OpenViking degraded ${marker}`);
  const result = await postMessage(
    page,
    sessionId,
    `${marker} 是什么？请根据 CodeAsk 知识回答，并说明来源。`,
  );

  expect(result.text.trim()).not.toEqual("");
  expect(result.text).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens|Input length/i);
  expect(result.text).toMatch(new RegExp(escapeRegExp(marker), "i"));
  expect(result.toolNames.some((toolName) => toolName.startsWith("openviking_"))).toBe(false);
  attachToolSample("degraded-fallback", result);
});

function attachToolSample(label: string, result: StreamResult) {
  const uniqueTools = Array.from(new Set(result.toolNames.filter(Boolean)));
  const sourceTools = uniqueTools.filter(
    (toolName) =>
      toolName.startsWith("openviking_") ||
      REPOSITORY_TOOLS.has(toolName) ||
      FILE_INSPECTION_TOOLS.has(toolName),
  );
  test.info().annotations.push({
    type: `tools:${label}`,
    description: JSON.stringify({
      sourceTools,
      uniqueTools,
      toolResultCount: result.toolResultTexts.length,
    }),
  });
}

async function ensureOpenVikingHealthy(page: import("@playwright/test").Page) {
  const status = await page.evaluate(async () => {
    const response = await fetch("/api/admin/openviking/status");
    if (!response.ok) {
      throw new Error(`OpenViking status failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as {
      degraded?: boolean;
      health?: { healthy?: boolean };
      ollama?: { model_available?: boolean };
      running?: boolean;
    };
  });
  test.skip(
    !status.running || !status.health?.healthy || !status.ollama?.model_available,
    `OpenViking is not ready: ${JSON.stringify(status)}`,
  );
}

async function ensureEnabledLlmConfig(page: import("@playwright/test").Page) {
  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{ enabled?: boolean }>;
  });
  test.skip(
    !llmConfigs.some((config) => config.enabled),
    "No enabled real LLM config is available in CodeAsk.",
  );
}

async function enqueueAndIndexManualResource(
  page: import("@playwright/test").Page,
  input: {
    content: string;
    featureSlug: string;
    filename: string;
    sourceId: string;
    sourceType: string;
    vikingUri: string;
  },
) {
  const job = await page.evaluate(async (payload) => {
    const response = await fetch("/api/admin/openviking/sync_jobs/enqueue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content: payload.content,
        feature_slug: payload.featureSlug,
        filename: payload.filename,
        source_id: payload.sourceId,
        source_type: payload.sourceType,
        viking_uri: payload.vikingUri,
      }),
    });
    if (!response.ok) {
      throw new Error(`enqueue failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as { id: string };
  }, input);

  await expect
    .poll(
      async () =>
        page.evaluate(async (jobId) => {
          const runResponse = await fetch("/api/admin/openviking/sync_jobs/run_pending", {
            method: "POST",
          });
          if (!runResponse.ok) {
            throw new Error(
              `run pending failed: ${runResponse.status} ${await runResponse.text()}`,
            );
          }
          const listResponse = await fetch("/api/admin/openviking/sync_jobs?limit=100");
          if (!listResponse.ok) {
            throw new Error(
              `list sync jobs failed: ${listResponse.status} ${await listResponse.text()}`,
            );
          }
          const jobs = (await listResponse.json()) as {
            items: Array<{ id: string; status: string }>;
          };
          return jobs.items.find((item) => item.id === jobId)?.status ?? "missing";
        }, job.id),
      { timeout: 240_000 },
    )
    .toBe("indexed");
}

async function createSession(page: import("@playwright/test").Page, title: string) {
  return page.evaluate(async ({ sessionTitle, subjectId }) => {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Subject-Id": subjectId },
      body: JSON.stringify({ title: sessionTitle }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  }, { sessionTitle: title, subjectId: ANON_SUBJECT_ID });
}

async function createFeature(
  page: import("@playwright/test").Page,
  input: { description: string; name: string },
) {
  return page.evaluate(async (payload) => {
    const response = await fetch("/api/features", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`create feature failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as { id: number; name: string; slug: string };
  }, input);
}

async function registerRepo(
  page: import("@playwright/test").Page,
  input: { localPath: string; name: string },
) {
  return page.evaluate(async (payload) => {
    const response = await fetch("/api/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: payload.name,
        source: "local_dir",
        local_path: payload.localPath,
      }),
    });
    if (!response.ok) {
      throw new Error(`register repo failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as { id: string; name: string };
  }, input);
}

async function uploadLegacyMarkdownDocument(
  page: import("@playwright/test").Page,
  input: { body: string; featureId: number; filename: string },
) {
  await page.evaluate(async (payload) => {
    const formData = new FormData();
    formData.append("feature_id", String(payload.featureId));
    formData.append(
      "file",
      new File([payload.body], payload.filename, { type: "text/markdown" }),
    );
    const response = await fetch("/api/documents", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(`upload wiki document failed: ${response.status} ${await response.text()}`);
    }
  }, input);
}

async function stopOpenVikingUntilDegraded(page: import("@playwright/test").Page) {
  const status = await getOpenVikingStatus(page);
  test.skip(
    typeof status.pid !== "number" || status.pid <= 0,
    `OpenViking process pid is unavailable: ${JSON.stringify(status)}`,
  );
  process.kill(status.pid as number, "SIGTERM");
  await expect
    .poll(async () => {
      const nextStatus = await getOpenVikingStatus(page);
      return !nextStatus.running || !nextStatus.health?.healthy;
    }, { timeout: 15_000 })
    .toBe(true);
}

async function getOpenVikingStatus(page: import("@playwright/test").Page) {
  return page.evaluate(async () => {
    const response = await fetch("/api/admin/openviking/status");
    if (!response.ok) {
      throw new Error(`OpenViking status failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as {
      health?: { healthy?: boolean };
      pid?: number;
      running?: boolean;
    };
  });
}

async function waitForRepoReady(page: import("@playwright/test").Page, repoId: string) {
  await expect
    .poll(
      async () =>
        page.evaluate(async (id) => {
          const response = await fetch(`/api/repos/${id}`);
          if (!response.ok) {
            throw new Error(`get repo failed: ${response.status} ${await response.text()}`);
          }
          return ((await response.json()) as { status: string }).status;
        }, repoId),
      { timeout: 120_000 },
    )
    .toBe("ready");
}

async function logout(page: import("@playwright/test").Page) {
  await page.evaluate(async () => {
    const response = await fetch("/api/auth/logout", { method: "POST" });
    if (!response.ok) {
      throw new Error(`logout failed: ${response.status} ${await response.text()}`);
    }
  });
}

async function postMessage(
  page: import("@playwright/test").Page,
  sessionId: string,
  content: string,
): Promise<StreamResult> {
  return page.evaluate(
    async ({ sessionId, content, subjectId }) => {
      const response = await fetch(`/api/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Subject-Id": subjectId },
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
      const toolResultTexts: string[] = [];

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

      function handleFrame(frame: string) {
        let eventType = "";
        const dataLines: string[] = [];
        for (const rawLine of frame.split(/\r?\n/)) {
          if (rawLine.startsWith("event:")) {
            eventType = rawLine.slice("event:".length).trim();
          } else if (rawLine.startsWith("data:")) {
            dataLines.push(rawLine.slice("data:".length).trimStart());
          }
        }
        if (!eventType) {
          return;
        }
        const data = dataLines.length > 0 ? JSON.parse(dataLines.join("\n")) : {};
        if (eventType === "text_delta") {
          text += String(data.delta ?? data.text ?? "");
        }
        if (eventType === "tool_call") {
          toolNames.push(String(data.tool_name ?? ""));
        }
        if (eventType === "tool_result") {
          toolResultTexts.push(JSON.stringify(data));
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
      return {
        text,
        toolNames: toolNames.filter(Boolean),
        toolResultTexts: toolResultTexts.filter(Boolean),
      };
    },
    { sessionId, content, subjectId: ANON_SUBJECT_ID },
  );
}

function referenceRepoPath(relativePath: string) {
  const root = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "..",
    "..",
  );
  return path.join(root, "references", relativePath);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
