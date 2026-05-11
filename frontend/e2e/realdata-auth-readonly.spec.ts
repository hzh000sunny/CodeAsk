import { expect, test, type Page, type TestInfo } from "@playwright/test";

const ENABLED = process.env.CODEASK_RUN_REAL_DATA_E2E === "1";
const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";
const EXPECTED_FEATURE_NAMES = parseCsv(process.env.CODEASK_REALDATA_EXPECT_FEATURES);
const EXPECTED_REPO_NAMES = parseCsv(process.env.CODEASK_REALDATA_EXPECT_REPOS);
const EXPECTED_LLM_NAMES = parseCsv(process.env.CODEASK_REALDATA_EXPECT_LLM_CONFIGS);
const WIKI_FEATURE_NAME = process.env.CODEASK_REALDATA_WIKI_FEATURE ?? "小米";
const WIKI_SEARCH_QUERY = process.env.CODEASK_REALDATA_WIKI_QUERY ?? "小米";
const WIKI_DOCUMENT_NAME = process.env.CODEASK_REALDATA_WIKI_DOCUMENT ?? "小米病历";

type Feature = {
  id: number;
  name: string;
};

type RepoList = {
  repos: Array<{ id: string; name: string }>;
};

type LlmConfig = {
  id: string;
  name: string;
  enabled: boolean;
};

type AuthMe = {
  authenticated: boolean;
  display_name: string;
  role: string;
  subject_id: string;
};

type WikiSearchResult = {
  items: Array<{
    node_id: number;
    title: string;
    path: string;
  }>;
};

test.describe.configure({ mode: "serial" });
test.skip(!ENABLED, "Set CODEASK_RUN_REAL_DATA_E2E=1 to run real-data readonly acceptance.");

test("anonymous can read real feature, wiki, and settings surfaces without write access", async ({
  page,
}, testInfo) => {
  await page.goto("/#/features", { waitUntil: "networkidle" });
  await expect(page.getByRole("region", { name: "特性列表" })).toBeVisible();
  await expect(page.getByLabel("搜索特性")).toBeVisible();

  const features = await page.evaluate(async () => {
    const response = await fetch("/api/features");
    if (!response.ok) {
      throw new Error(`list features failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as Feature[];
  });
  expect(features.length).toBeGreaterThan(0);
  for (const featureName of EXPECTED_FEATURE_NAMES) {
    expect(features.some((item) => item.name === featureName), `missing feature ${featureName}`).toBe(
      true,
    );
  }

  const wikiFeature = pickFeature(features, WIKI_FEATURE_NAME);
  await page.getByLabel("搜索特性").fill(wikiFeature.name);
  await expect(page.getByRole("heading", { name: wikiFeature.name })).toBeVisible();
  await saveScreenshot(page, testInfo, "features-anonymous.png");

  const wikiHit = await page.evaluate(async ({ featureId, query, title }) => {
    const response = await fetch(
      `/api/wiki/search?feature_id=${featureId}&q=${encodeURIComponent(query)}`,
    );
    if (!response.ok) {
      throw new Error(`wiki search failed: ${response.status} ${await response.text()}`);
    }
    const payload = (await response.json()) as WikiSearchResult;
    const match = payload.items.find((item) => item.title === title) ?? payload.items[0] ?? null;
    if (!match) {
      throw new Error(`wiki search returned no results for ${query}`);
    }
    return match;
  }, { featureId: wikiFeature.id, query: WIKI_SEARCH_QUERY, title: WIKI_DOCUMENT_NAME });

  await page.goto(`/#/wiki?feature=${wikiFeature.id}&node=${wikiHit.node_id}`, {
    waitUntil: "networkidle",
  });
  await expect(page.getByText("当前特性")).toBeVisible();
  await expect(page.getByRole("heading", { name: WIKI_DOCUMENT_NAME })).toBeVisible();
  await expect(page.getByText("基本情况")).toBeVisible();
  await expect(page.locator(".wiki-reader-body img").first()).toBeVisible();
  await page.reload({ waitUntil: "networkidle" });
  await expect(page).toHaveURL(new RegExp(`#\\/wiki\\?feature=${wikiFeature.id}&node=${wikiHit.node_id}`));
  await expect(page.getByText("基本情况")).toBeVisible();
  await saveScreenshot(page, testInfo, "wiki-anonymous.png");

  await page.goto("/#/settings", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "用户配置" })).toBeVisible();
  await expect(page.getByText("未登录访客")).toBeVisible();
  await saveScreenshot(page, testInfo, "settings-anonymous.png");
});

test("admin sees preserved real configs, repos, and cached login identity", async ({
  page,
}, testInfo) => {
  await loginFromUi(page, ADMIN_USERNAME, ADMIN_PASSWORD);
  await expect(page.getByRole("button", { name: "Admin", exact: true })).toBeVisible();

  const me = await page.evaluate(async () => {
    const response = await fetch("/api/auth/me");
    if (!response.ok) {
      throw new Error(`auth me failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as AuthMe;
  });
  expect(me.authenticated).toBe(true);
  expect(me.role).toBe("admin");

  await page.goto("/#/settings", { waitUntil: "networkidle" });
  await expect(page.getByRole("heading", { name: "会话附件" })).toBeVisible();

  const llmConfigs = await page.evaluate(async () => {
    const response = await fetch("/api/admin/llm-configs");
    if (!response.ok) {
      throw new Error(`list llm configs failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as LlmConfig[];
  });
  expect(llmConfigs.length).toBeGreaterThan(0);
  for (const name of EXPECTED_LLM_NAMES) {
    expect(llmConfigs.some((item) => item.name === name), `missing llm config ${name}`).toBe(true);
  }

  const repos = await page.evaluate(async () => {
    const response = await fetch("/api/repos");
    if (!response.ok) {
      throw new Error(`list repos failed: ${response.status} ${await response.text()}`);
    }
    return (await response.json()) as RepoList;
  });
  expect(repos.repos.length).toBeGreaterThan(0);
  for (const name of EXPECTED_REPO_NAMES) {
    expect(repos.repos.some((item) => item.name === name), `missing repo ${name}`).toBe(true);
  }

  await expect(page.getByText("火山-Anthropic-glm-5.1")).toBeVisible();
  await expect(page.getByText("E2E claude-code 1778123017269")).toBeVisible();
  await saveScreenshot(page, testInfo, "settings-admin.png");

  await page.getByRole("button", { name: "Admin", exact: true }).click();
  await page.getByRole("menuitem", { name: "退出" }).click();
  await expect(page.getByRole("button", { name: "未登录" })).toBeVisible();

  await page.getByRole("button", { name: "未登录" }).click();
  await page.getByRole("menuitem", { name: "登录" }).click();
  await expect(page).toHaveURL(/#\/login$/);
  await expect(page.getByLabel("用户名")).toHaveValue(ADMIN_USERNAME);
  await saveScreenshot(page, testInfo, "login-cached-username.png");
});

async function loginFromUi(page: Page, username: string, password: string) {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(username);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

function parseCsv(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function pickFeature(features: Feature[], expectedName: string): Feature {
  return features.find((item) => item.name === expectedName) ?? features[0];
}

async function saveScreenshot(page: Page, testInfo: TestInfo, filename: string) {
  await page.screenshot({
    path: testInfo.outputPath(filename),
    fullPage: true,
  });
}
