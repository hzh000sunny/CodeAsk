import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

const SUBJECT_ID = "refresh_live@dev";
const SUBJECT_KEY = "codeask.subject_id";

test("top-level pages keep their route after reload against the real app", async ({
  page,
  request,
}, testInfo) => {
  const featureId = await createFeature(request, "Live Route Refresh");
  await setSubjectIdentity(page, SUBJECT_ID);

  await page.goto("/#/sessions");
  await expect(page.getByPlaceholder("搜索会话")).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("搜索会话")).toBeVisible();
  await expect(page).toHaveURL(/#\/sessions$/);
  await saveScreenshot(page, testInfo, "sessions-after-reload.png");

  await page.goto("/#/features");
  await expect(page.getByPlaceholder("搜索特性")).toBeVisible();
  await page.reload();
  await expect(page.getByPlaceholder("搜索特性")).toBeVisible();
  await expect(page).toHaveURL(/#\/features$/);
  await saveScreenshot(page, testInfo, "features-after-reload.png");

  await page.goto(`/#/wiki?feature=${featureId}`);
  await expect(page.getByText("当前特性")).toBeVisible();
  await page.reload();
  await expect(page.getByText("当前特性")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`#\\/wiki\\?feature=${featureId}(?:&node=\\d+)?$`));
  await saveScreenshot(page, testInfo, "wiki-after-reload.png");

  await page.goto("/#/settings");
  await expect(page.getByRole("heading", { name: "用户配置" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "用户配置" })).toBeVisible();
  await expect(page).toHaveURL(/#\/settings$/);
  await saveScreenshot(page, testInfo, "settings-after-reload.png");
});

async function createFeature(request: APIRequestContext, name: string): Promise<number> {
  const response = await request.post("/api/features", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    data: {
      name: `${name} ${Date.now()}`,
      description: "Playwright live route refresh verification",
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return Number(body.id);
}

async function setSubjectIdentity(page: Page, subjectId: string) {
  await page.addInitScript(
    (payload: string[]) => {
      const [key, value] = payload;
      window.localStorage.setItem(key, value);
    },
    [SUBJECT_KEY, subjectId],
  );
}

async function saveScreenshot(page: Page, testInfo: TestInfo, filename: string) {
  await page.screenshot({
    path: testInfo.outputPath(filename),
    fullPage: true,
  });
}
