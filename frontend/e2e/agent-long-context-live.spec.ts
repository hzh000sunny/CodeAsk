import { expect, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_AGENT_LONG_CONTEXT_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const LLM_API_KEY = process.env.CODEASK_LIVE_AGENT_LLM_API_KEY;
const LLM_BASE_URL =
  process.env.CODEASK_LIVE_AGENT_LLM_BASE_URL ??
  "https://ark.cn-beijing.volces.com/api/coding/v3";
const LLM_MODEL = process.env.CODEASK_LIVE_AGENT_LLM_MODEL ?? "GLM-5.1";
const LLM_PROTOCOL = process.env.CODEASK_LIVE_AGENT_LLM_PROTOCOL ?? "openai";

test.describe.configure({ timeout: 900_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_AGENT_LONG_CONTEXT_E2E=1 to run live long-context E2E.",
);

test("long conversation keeps usable context after conversation summary", async ({ page }) => {
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
      body: JSON.stringify({ title: `Long context live ${Date.now()}` }),
    });
    if (!response.ok) {
      throw new Error(`create session failed: ${response.status} ${await response.text()}`);
    }
    return ((await response.json()) as { id: string }).id;
  });

  const seedQuestions = [
    "Python 中 list 和 tuple 的区别是什么？",
    "你刚刚提到哪个是不可变的？",
    "写一个函数反转字符串",
    "把上一轮总结成一句话",
    "grep 和 awk 的区别？",
    "TCP 三次握手过程？",
    "索引为什么能加速查询？",
  ];
  for (const question of seedQuestions) {
    const answer = await postMessage(page, sessionId, question);
    expect(answer).not.toEqual("");
    expect(answer).not.toMatch(/第一次交流|无法跨对话|Input length|BadRequestError|Agent 运行失败/i);
  }

  await postMessage(page, sessionId, "刷新前追问：你上一轮说了什么？");

  await page.reload({ waitUntil: "networkidle" });
  const finalAnswer = await postMessage(page, sessionId, "继续回答：上一轮你回答的主题是什么？");
  expect(finalAnswer).not.toEqual("");
  expect(finalAnswer).not.toMatch(/第一次交流|无法跨对话|没有给出过回答/i);
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
          name: `Live Long Context ${Date.now()}`,
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

async function postMessage(
  page: import("@playwright/test").Page,
  sessionId: string,
  content: string,
): Promise<string> {
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
        if (eventType === "error") {
          throw new Error(`agent error: ${JSON.stringify(data)}`);
        }
      }
      return text.trim();
    },
    { sessionId, content },
  );
}
