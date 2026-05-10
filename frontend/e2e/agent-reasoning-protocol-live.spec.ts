import { expect, test } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

type LlmConfig = {
  id: string;
  name: string;
  protocol: string;
  base_url: string | null;
  model_name: string;
  enabled: boolean;
  reasoning_profile?: string;
};

type StreamResult = {
  text: string;
  eventTypes: string[];
  reasoningObserved: Array<Record<string, unknown>>;
  leakDetected: Array<Record<string, unknown>>;
};

test.describe.configure({ timeout: 900_000 });
test.skip(
  !ENABLED,
  "Set CODEASK_RUN_LIVE_REASONING_PROTOCOL_E2E=1 to run live reasoning protocol E2E.",
);

test("structured reasoning is isolated for each enabled LLM config", async ({ page }) => {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();

  const configs = await listEnabledLlmConfigs(page);
  test.skip(configs.length === 0, "No enabled LLM configs available for live reasoning E2E.");

  const originalEnabled = new Map(configs.map((config) => [config.id, config.enabled]));
  const observations: Array<{
    config: Pick<LlmConfig, "name" | "protocol" | "model_name" | "reasoning_profile">;
    result: StreamResult;
  }> = [];

  try {
    for (const config of configs) {
      await selectOnlyConfig(page, configs, config.id);
      const sessionId = await createSession(page, `Reasoning protocol ${config.name} ${Date.now()}`);
      const result = await postMessage(page, sessionId, "请只回复一句：OK。");
      observations.push({
        config: {
          name: config.name,
          protocol: config.protocol,
          model_name: config.model_name,
          reasoning_profile: config.reasoning_profile,
        },
        result,
      });

      expect(result.text.trim(), `${config.name} visible answer`).not.toEqual("");
      expect(result.text, `${config.name} visible answer`).not.toMatch(/<think>|<\/think>/i);

      const turns = await listTurns(page, sessionId);
      const persisted = turns.map((turn) => turn.content).join("\n");
      expect(persisted, `${config.name} persisted turns`).toContain(result.text.trim().slice(0, 2));
      expect(persisted, `${config.name} persisted turns`).not.toMatch(/<think>|<\/think>/i);

      const traces = await listTraces(page, sessionId);
      const reasoningTraces = traces.filter((trace) => trace.event_type === "reasoning_observed");
      for (const trace of reasoningTraces) {
        expect(JSON.stringify(trace.payload), `${config.name} reasoning trace`).not.toMatch(
          /内部思考|chain of thought|<think>/i,
        );
      }
    }
  } finally {
    await restoreEnabledState(page, originalEnabled);
  }

  expect(
    observations,
    `reasoning observations: ${JSON.stringify(observations, null, 2)}`,
  ).not.toHaveLength(0);
});

async function listEnabledLlmConfigs(page: import("@playwright/test").Page) {
  const configs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as LlmConfig[];
  });
  const filter = process.env.CODEASK_LIVE_REASONING_MODELS;
  if (!filter) {
    return configs.filter((config) => config.enabled);
  }
  const names = filter
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
  return configs.filter(
    (config) =>
      config.enabled &&
      names.some(
        (name) =>
          config.name.toLowerCase().includes(name) ||
          config.model_name.toLowerCase().includes(name),
      ),
  );
}

async function selectOnlyConfig(
  page: import("@playwright/test").Page,
  configs: LlmConfig[],
  selectedId: string,
) {
  for (const config of configs) {
    const response = await page.evaluate(
      async ({ id, enabled }) => {
        const patch = await fetch(`/api/admin/llm-configs/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
        return { ok: patch.ok, status: patch.status, text: await patch.text() };
      },
      { id: config.id, enabled: config.id === selectedId },
    );
    if (!response.ok) {
      throw new Error(`toggle config failed: ${response.status} ${response.text}`);
    }
  }
}

async function restoreEnabledState(
  page: import("@playwright/test").Page,
  states: Map<string, boolean>,
) {
  for (const [id, enabled] of states) {
    await page.evaluate(
      async ({ id, enabled }) => {
        await fetch(`/api/admin/llm-configs/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled }),
        });
      },
      { id, enabled },
    );
  }
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

async function listTurns(page: import("@playwright/test").Page, sessionId: string) {
  return page.evaluate(async (sessionId) => {
    const response = await fetch(`/api/sessions/${sessionId}/turns`);
    if (!response.ok) {
      throw new Error(`list turns failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{ role: string; content: string }>;
  }, sessionId);
}

async function listTraces(page: import("@playwright/test").Page, sessionId: string) {
  return page.evaluate(async (sessionId) => {
    const response = await fetch(`/api/sessions/${sessionId}/traces`);
    if (!response.ok) {
      throw new Error(`list traces failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Array<{
      event_type: string;
      payload: Record<string, unknown>;
    }>;
  }, sessionId);
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
      const eventTypes: string[] = [];
      const reasoningObserved: Array<Record<string, unknown>> = [];
      const leakDetected: Array<Record<string, unknown>> = [];

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
          data:
            dataLines.length > 0
              ? JSON.parse(dataLines.join("\n")) as Record<string, unknown>
              : {},
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
        if (eventType === "reasoning_observed") {
          reasoningObserved.push(data);
        }
        if (eventType === "reasoning_leak_detected") {
          leakDetected.push(data);
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
      return { text, eventTypes, reasoningObserved, leakDetected };
    },
    { sessionId, content },
  );
}
