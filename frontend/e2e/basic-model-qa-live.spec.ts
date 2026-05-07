import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ENABLED = process.env.CODEASK_RUN_LIVE_BASIC_QA_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const LLM_API_KEY = process.env.CODEASK_LIVE_AGENT_LLM_API_KEY;
const LLM_BASE_URL =
  process.env.CODEASK_LIVE_AGENT_LLM_BASE_URL ??
  "https://ark.cn-beijing.volces.com/api/coding/v3";
const LLM_MODEL = process.env.CODEASK_LIVE_AGENT_LLM_MODEL ?? "GLM-5.1";
const LLM_PROTOCOL = process.env.CODEASK_LIVE_AGENT_LLM_PROTOCOL ?? "openai";
const ALLOWED_TOOL_TRIGGER_RATE = 0.1;

type BasicQaCase = {
  id: string;
  input: { question: string; category: string };
};

type StreamResult = {
  text: string;
  toolNames: string[];
  eventTypes: string[];
};

test.describe.configure({ timeout: 900_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_BASIC_QA_E2E=1 to run the live basic Q&A model baseline.",
);

test("basic model questions stay model-led in one frontend session", async ({ page }) => {
  const cases = loadCases();

  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
  await ensureLlmConfig(page);

  const sessionId = await page.evaluate(async () => {
    const response = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: `Basic QA live ${Date.now()}` }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  });

  const deviations: Array<{ id: string; question: string; tools: string[] }> = [];
  for (const qaCase of cases) {
    const result = await postMessage(page, sessionId, qaCase.input.question);
    expect(result.text.trim(), qaCase.id).not.toEqual("");
    expect(result.text, qaCase.id).not.toMatch(/BadRequestError|Agent 运行失败|max_tokens/i);
    const toolNames = Array.from(new Set(result.toolNames));
    if (toolNames.length > 0) {
      deviations.push({ id: qaCase.id, question: qaCase.input.question, tools: toolNames });
    }
  }

  const turns = await page.evaluate(async (id) => {
    const response = await fetch(`/api/sessions/${id}/turns`);
    if (!response.ok) {
      throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{ role: string; content: string }>;
  }, sessionId);
  expect(turns.filter((turn) => turn.role === "user")).toHaveLength(cases.length);
  expect(turns.filter((turn) => turn.role === "agent")).toHaveLength(cases.length);

  const allowed = Math.floor(cases.length * ALLOWED_TOOL_TRIGGER_RATE);
  expect(
    deviations.length,
    `basic QA tool deviations exceed baseline: ${JSON.stringify(deviations, null, 2)}`,
  ).toBeLessThanOrEqual(allowed);
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
          name: `Live Basic QA ${Date.now()}`,
          protocol,
          base_url: baseUrl,
          api_key: apiKey,
          model_name: model,
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

      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const eventLine = frame.split("\n").find((line) => line.startsWith("event: "));
          const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
          const eventType = eventLine?.slice("event: ".length).trim();
          if (eventType) {
            eventTypes.push(eventType);
          }
          if (!dataLine) {
            continue;
          }
          const data = JSON.parse(dataLine.slice("data: ".length));
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
      return { text, toolNames: toolNames.filter(Boolean), eventTypes };
    },
    { sessionId, content },
  );
}

function loadCases(): BasicQaCase[] {
  const currentFile = fileURLToPath(import.meta.url);
  const repoRoot = path.resolve(path.dirname(currentFile), "../..");
  const file = path.join(repoRoot, "evals/basic_qa/cases/seed_001.jsonl");
  return readFileSync(file, "utf8")
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as BasicQaCase);
}
