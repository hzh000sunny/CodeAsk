import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const SUBJECT_ID = "live_e2e@dev";
const SUBJECT_KEY = "codeask.subject_id";

test("wiki import succeeds against the real backend and opens the imported document", async ({
  page,
  request,
}) => {
  const featureId = await createFeature(request, "Live Wiki Import Success");
  const importDir = await createWikiImportDirectory({
    rootName: "ops-success",
    markdownFiles: [
      {
        relativePath: "Runbook.md",
        body: "# Runbook\n\n![Logo](./images/logo.png)\n\n真实后端导入成功。",
      },
    ],
    assetFiles: [{ relativePath: "images/logo.png", content: PNG_BYTES }],
    ignoredFiles: [{ relativePath: "raw/trace.log", content: "ignored log" }],
  });

  await setSubjectIdentity(page, SUBJECT_ID);
  await page.goto(`/#/wiki?feature=${featureId}`);

  await expect(page.getByRole("heading", { name: "开始建设这个特性的 Wiki" })).toBeVisible();
  await openKnowledgeBaseImportDialog(page);
  await page.getByLabel("选择 Wiki 目录").setInputFiles(importDir);

  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`#\\/wiki\\?feature=${featureId}&node=\\d+`));
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Runbook");
  await expect(page.getByText("真实后端导入成功。")).toBeVisible();

  const image = page.locator(".wiki-reader img");
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute("src", /\/api\/wiki\/assets\/\d+\/content/);
});

test("wiki import shows a real conflict queue and can overwrite to finish", async ({
  page,
  request,
}) => {
  const featureId = await createFeature(request, "Live Wiki Import Conflict");
  await uploadLegacyMarkdownDocument(request, {
    featureId,
    filename: "Guide.md",
    body: "# Guide\n\n旧版本内容。",
  });
  const importDir = await createWikiImportDirectory({
    rootName: "ops-conflict",
    markdownFiles: [
      {
        relativePath: "Guide.md",
        body: "# Guide\n\n![Logo](./images/logo.png)\n\n导入版本内容。",
      },
    ],
    assetFiles: [{ relativePath: "images/logo.png", content: PNG_BYTES }],
    ignoredFiles: [{ relativePath: "raw/trace.log", content: "ignored log" }],
  });

  await setSubjectIdentity(page, SUBJECT_ID);
  await page.goto(`/#/wiki?feature=${featureId}`);

  await openKnowledgeBaseImportDialog(page);
  const dialog = page.getByRole("dialog");
  await page.getByLabel("选择 Wiki 目录").setInputFiles(importDir);

  await expect(page.getByText("冲突 1")).toBeVisible();
  await expect(page.getByText("已上传 1")).toBeVisible();
  await expect(dialog.getByText("ops-conflict/Guide.md", { exact: true })).toBeVisible();
  await expect(dialog.getByText("知识库 / guide", { exact: true })).toBeVisible();
  await expect(dialog.getByText("ops-conflict/images/logo.png", { exact: true })).toBeVisible();
  await expect(dialog.getByText("知识库 / images / logo.png", { exact: true })).toBeVisible();
  await expect(dialog.getByText(/wiki node path conflict:/)).toBeVisible();
  await expect(page.getByRole("button", { name: "已忽略 1" })).toBeVisible();
  await expect(page.getByText("ops-conflict/raw/trace.log")).toHaveCount(0);

  await page.getByRole("button", { name: "已忽略 1" }).click();
  await expect(page.getByText("ops-conflict/raw/trace.log")).toBeVisible();
  await page.getByRole("button", { name: "冲突 1" }).click();
  await expect(page.getByRole("button", { name: "覆盖", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "覆盖", exact: true }).click();

  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(new RegExp(`#\\/wiki\\?feature=${featureId}&node=\\d+`));
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Guide");
  await expect(page.getByText("导入版本内容。")).toBeVisible();
});

async function createFeature(request: APIRequestContext, name: string): Promise<number> {
  const response = await request.post("/api/features", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    data: {
      name: `${name} ${Date.now()}`,
      description: "Playwright live wiki import verification",
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return Number(body.id);
}

async function uploadLegacyMarkdownDocument(
  request: APIRequestContext,
  payload: {
    featureId: number;
    filename: string;
    body: string;
  },
) {
  const response = await request.post("/api/documents", {
    headers: { "X-Subject-Id": SUBJECT_ID },
    multipart: {
      feature_id: String(payload.featureId),
      file: {
        name: payload.filename,
        mimeType: "text/markdown",
        buffer: Buffer.from(payload.body, "utf-8"),
      },
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function openKnowledgeBaseImportDialog(page: Page) {
  await expect(page.getByRole("complementary", { name: "Wiki 目录树" })).toBeVisible();
  await page.getByRole("button", { name: "打开节点 知识库 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "导入 Wiki" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
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

async function createWikiImportDirectory(payload: {
  rootName: string;
  markdownFiles: Array<{ relativePath: string; body: string }>;
  assetFiles: Array<{ relativePath: string; content: Buffer }>;
  ignoredFiles: Array<{ relativePath: string; content: string }>;
}) {
  const root = await mkdtemp(path.join(tmpdir(), "codeask-live-wiki-import-"));
  const dir = path.join(root, payload.rootName);

  for (const file of payload.markdownFiles) {
    const fullPath = path.join(dir, file.relativePath);
    await mkdir(path.dirname(fullPath), { recursive: true });
    await writeFile(fullPath, file.body, "utf-8");
  }
  for (const file of payload.assetFiles) {
    const fullPath = path.join(dir, file.relativePath);
    await mkdir(path.dirname(fullPath), { recursive: true });
    await writeFile(fullPath, file.content);
  }
  for (const file of payload.ignoredFiles) {
    const fullPath = path.join(dir, file.relativePath);
    await mkdir(path.dirname(fullPath), { recursive: true });
    await writeFile(fullPath, file.content, "utf-8");
  }

  return dir;
}

const PNG_BYTES = Buffer.from(
  [
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d,
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1f, 0x15, 0xc4, 0x89, 0x00, 0x00, 0x00,
    0x0c, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
    0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xdd, 0x8d, 0xb1, 0x00, 0x00, 0x00,
    0x00, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
  ],
);
