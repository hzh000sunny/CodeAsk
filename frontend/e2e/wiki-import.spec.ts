import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type Page, type Route } from "@playwright/test";

const feature = {
  id: 7,
  name: "支付结算",
  slug: "payment-settlement",
  description: "支付链路知识域",
  owner_subject_id: "client_e2e",
  summary_text: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

type WikiImportScenario = "directory_queue" | "conflict_resolve" | "retry_failed";

test("wiki directory import keeps ignored files folded and strips the local root shell", async ({
  page,
}) => {
  let scannedItems: Array<{
    relative_path: string;
    item_kind: string;
    included: boolean;
    ignore_reason?: string | null;
  }> = [];
  await installWikiImportMocks(page, {
    scenario: "directory_queue",
    onScan: (items) => {
      scannedItems = items;
    },
  });
  await page.goto("/#/wiki");

  await openWikiImportDialog(page);

  const rootDir = await mkdtemp(path.join(tmpdir(), "codeask-wiki-import-"));
  const opsDir = path.join(rootDir, "ops");
  await mkdir(path.join(opsDir, "images"), { recursive: true });
  await mkdir(path.join(opsDir, "raw"), { recursive: true });
  await writeFile(
    path.join(opsDir, "Guide.md"),
    "# Guide\n\n![Logo](./images/logo.png)\n\nSee [Sibling](./Guide.md)\n",
    "utf-8",
  );
  await writeFile(path.join(opsDir, "images", "logo.png"), PNG_BYTES);
  await writeFile(path.join(opsDir, "raw", "trace.log"), "debug log", "utf-8");

  await page.getByLabel("选择 Wiki 目录").setInputFiles(opsDir);

  await expect.poll(() => scannedItems.length).toBe(3);
  expect(scannedItems).toEqual([
    {
      relative_path: "ops/Guide.md",
      item_kind: "document",
      included: true,
      ignore_reason: null,
    },
    {
      relative_path: "ops/images/logo.png",
      item_kind: "asset",
      included: true,
      ignore_reason: null,
    },
    {
      relative_path: "ops/raw/trace.log",
      item_kind: "ignored",
      included: false,
      ignore_reason: "not_referenced",
    },
  ]);

  await expect(page.getByText("已选择目录 ops（2 个可导入文件）")).toBeVisible();
  await expect(
    page.getByText("已忽略 1 个非 Wiki 文件，仅保留 Markdown 和被 Markdown 引用的静态资源。"),
  ).toBeVisible();
  await expect(page.getByText("ops/Guide.md")).toBeVisible();
  await expect(page.getByText("知识库 / guide")).toBeVisible();
  await expect(page.getByText("ops/images/logo.png", { exact: true })).toBeVisible();
  await expect(page.getByText("知识库 / images / logo.png")).toBeVisible();
  await expect(page.getByRole("button", { name: "已忽略 1" })).toBeVisible();
  await expect(page.getByText("ops/raw/trace.log")).toHaveCount(0);
  await page.getByRole("button", { name: "已忽略 1" }).click();
  await expect(page.getByText("ops/raw/trace.log")).toBeVisible();
});

test("wiki import keeps later files moving after a conflict and completes after overwrite", async ({
  page,
}) => {
  await installWikiImportMocks(page, { scenario: "conflict_resolve" });
  await page.goto("/#/wiki");

  await openWikiImportDialog(page);

  await page.getByLabel("选择 Markdown 文件").setInputFiles([
    {
      name: "Runbook.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Runbook\n\nconflict first"),
    },
    {
      name: "Guide.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Guide\n\nsecond continues"),
    },
  ]);

  await expect(page.getByText("冲突 1")).toBeVisible();
  await expect(page.getByText("已上传 1")).toBeVisible();
  await expect(page.getByText("Runbook.md")).toBeVisible();
  await expect(page.getByText("冲突待处理")).toBeVisible();
  await expect(page.getByRole("button", { name: "覆盖", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "全部覆盖" })).toBeVisible();

  await page.getByRole("button", { name: "覆盖", exact: true }).click();

  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/#\/wiki\?feature=7&node=707/);
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Runbook");
  await expect(page.getByText("冲突解决后导入完成。")).toBeVisible();
});

test("wiki import can retry failed items in batch and then opens the imported document", async ({
  page,
}) => {
  await installWikiImportMocks(page, { scenario: "retry_failed" });
  await page.goto("/#/wiki");

  await openWikiImportDialog(page);

  await page.getByLabel("选择 Markdown 文件").setInputFiles([
    {
      name: "Runbook.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Runbook\n\nfirst upload fails"),
    },
    {
      name: "Guide.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Guide\n\nsecond upload succeeds"),
    },
  ]);

  await expect(page.getByText("失败 1")).toBeVisible();
  await expect(page.getByText("已上传 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试失败项" })).toBeVisible();

  await page.getByRole("button", { name: "重试失败项" }).click();

  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page).toHaveURL(/#\/wiki\?feature=7&node=709/);
  await expect(page.locator(".wiki-page-header h1")).toHaveText("Runbook");
  await expect(page.getByText("批量重试后导入完成。")).toBeVisible();
});

async function openWikiImportDialog(page: Page) {
  const primaryNav = page.getByRole("navigation", { name: "主导航" });
  await primaryNav.getByRole("button", { name: "Wiki", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Wiki 目录树" })).toBeVisible();
  await page.getByRole("button", { name: "打开节点 知识库 的更多操作" }).click();
  await page.getByRole("menuitem", { name: "导入 Wiki" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function installWikiImportMocks(
  page: Page,
  options: {
    scenario: WikiImportScenario;
    onScan?: (
      items: Array<{
        relative_path: string;
        item_kind: string;
        included: boolean;
        ignore_reason?: string | null;
      }>,
    ) => void;
  },
) {
  let directoryStage: "initial" | "after_first_failure" | "after_second_uploaded" = "initial";
  let conflictStage: "initial" | "after_first_conflict" | "after_second_uploaded" | "completed" =
    "initial";
  let retryStage: "initial" | "after_first_failure" | "after_second_uploaded" | "completed" =
    "initial";

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathWithQuery = `${url.pathname}${url.search}`;
    const method = request.method();

    if (pathWithQuery === "/api/auth/me" && method === "GET") {
      return json(route, {
        subject_id: "client_e2e",
        display_name: "client_e2e",
        role: "member",
        authenticated: false,
      });
    }
    if (pathWithQuery === "/api/sessions" && method === "GET") {
      return json(route, []);
    }
    if (pathWithQuery === "/api/features" && method === "GET") {
      return json(route, [feature]);
    }
    if (pathWithQuery === "/api/wiki/tree" && method === "GET") {
      return json(route, {
        space: null,
        nodes: buildWikiTreeNodes(options.scenario, conflictStage, retryStage),
      });
    }
    if (pathWithQuery === "/api/wiki/spaces/by-feature/7" && method === "GET") {
      return json(route, {
        id: 70,
        feature_id: 7,
        scope: "current",
        display_name: "支付结算",
        slug: "payment-settlement",
        status: "ready",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00",
      });
    }
    if (pathWithQuery === "/api/wiki/reports/projections?feature_id=7" && method === "GET") {
      return json(route, { items: [] });
    }
    if (pathWithQuery === "/api/me/llm-configs" && method === "GET") {
      return json(route, []);
    }

    if (options.scenario === "directory_queue") {
      if (pathWithQuery === "/api/wiki/import-sessions" && method === "POST") {
        return json(route, buildDirectorySessionSummary(directoryStage), 201);
      }
      if (pathWithQuery === "/api/wiki/import-sessions/431/scan" && method === "POST") {
        const payload = request.postDataJSON() as {
          items: Array<{
            relative_path: string;
            item_kind: string;
            included: boolean;
            ignore_reason?: string | null;
          }>;
        };
        options.onScan?.(payload.items);
        return json(route, buildDirectorySessionSummary(directoryStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/431" && method === "GET") {
        return json(route, buildDirectorySessionSummary(directoryStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/431/items" && method === "GET") {
        return json(route, { items: buildDirectoryItems(directoryStage) });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/431/items/1/upload" && method === "POST") {
        directoryStage = "after_first_failure";
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "first upload failed" }),
        });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/431/items/2/upload" && method === "POST") {
        directoryStage = "after_second_uploaded";
        return json(route, {
          session: buildDirectorySessionSummary(directoryStage),
          item: buildDirectoryItems(directoryStage)[1],
        });
      }
    }

    if (options.scenario === "conflict_resolve") {
      if (pathWithQuery === "/api/wiki/import-sessions" && method === "POST") {
        return json(route, buildConflictSessionSummary(conflictStage), 201);
      }
      if (pathWithQuery === "/api/wiki/import-sessions/432/scan" && method === "POST") {
        return json(route, buildConflictSessionSummary(conflictStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/432" && method === "GET") {
        return json(route, buildConflictSessionSummary(conflictStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/432/items" && method === "GET") {
        return json(route, { items: buildConflictItems(conflictStage) });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/432/items/1/upload" && method === "POST") {
        conflictStage = "after_first_conflict";
        return json(route, {
          session: buildConflictSessionSummary(conflictStage),
          item: buildConflictItems(conflictStage)[0],
        });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/432/items/2/upload" && method === "POST") {
        conflictStage = "after_second_uploaded";
        return json(route, {
          session: buildConflictSessionSummary(conflictStage),
          item: buildConflictItems(conflictStage)[1],
        });
      }
      if (
        pathWithQuery === "/api/wiki/import-sessions/432/items/1/resolve" &&
        method === "POST"
      ) {
        conflictStage = "completed";
        return json(route, {
          session: buildConflictSessionSummary(conflictStage),
          item: buildConflictItems(conflictStage)[0],
        });
      }
      if (pathWithQuery === "/api/wiki/documents/707" && method === "GET") {
        return json(route, buildDocumentDetail(707, "Runbook", "# Runbook\n\n冲突解决后导入完成。"));
      }
      if (pathWithQuery === "/api/wiki/documents/707/versions" && method === "GET") {
        return json(route, buildDocumentVersions(707));
      }
    }

    if (options.scenario === "retry_failed") {
      if (pathWithQuery === "/api/wiki/import-sessions" && method === "POST") {
        return json(route, buildRetrySessionSummary(retryStage), 201);
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433/scan" && method === "POST") {
        return json(route, buildRetrySessionSummary(retryStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433" && method === "GET") {
        return json(route, buildRetrySessionSummary(retryStage));
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433/items" && method === "GET") {
        return json(route, { items: buildRetryItems(retryStage) });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433/items/1/upload" && method === "POST") {
        retryStage = "after_first_failure";
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "first upload failed" }),
        });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433/items/2/upload" && method === "POST") {
        retryStage = "after_second_uploaded";
        return json(route, {
          session: buildRetrySessionSummary(retryStage),
          item: buildRetryItems(retryStage)[1],
        });
      }
      if (pathWithQuery === "/api/wiki/import-sessions/433/retry" && method === "POST") {
        retryStage = "completed";
        return json(route, buildRetrySessionSummary(retryStage));
      }
      if (pathWithQuery === "/api/wiki/documents/709" && method === "GET") {
        return json(route, buildDocumentDetail(709, "Runbook", "# Runbook\n\n批量重试后导入完成。"));
      }
      if (pathWithQuery === "/api/wiki/documents/709/versions" && method === "GET") {
        return json(route, buildDocumentVersions(709));
      }
    }

    throw new Error(`Unexpected ${method} ${pathWithQuery}`);
  });
}

function json(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function buildWikiTreeNodes(
  scenario: WikiImportScenario,
  conflictStage: "initial" | "after_first_conflict" | "after_second_uploaded" | "completed",
  retryStage: "initial" | "after_first_failure" | "after_second_uploaded" | "completed",
) {
  const importedNodes =
    scenario === "conflict_resolve" && conflictStage === "completed"
      ? [
          wikiDocumentNode(707, "Runbook", "knowledge-base/runbook"),
          wikiDocumentNode(708, "Guide", "knowledge-base/guide"),
        ]
      : scenario === "retry_failed" && retryStage === "completed"
        ? [
            wikiDocumentNode(709, "Runbook", "knowledge-base/runbook"),
            wikiDocumentNode(710, "Guide", "knowledge-base/guide"),
          ]
        : [];

  return [
    {
      id: -1,
      space_id: 0,
      feature_id: null,
      parent_id: null,
      type: "folder",
      name: "当前特性",
      path: "当前特性",
      system_role: "feature_group_current",
      sort_order: 0,
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
    },
    {
      id: -2,
      space_id: 0,
      feature_id: null,
      parent_id: null,
      type: "folder",
      name: "历史特性",
      path: "历史特性",
      system_role: "feature_group_history",
      sort_order: 1,
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
    },
    {
      id: -100007,
      space_id: 70,
      feature_id: 7,
      parent_id: -1,
      type: "folder",
      name: "支付结算",
      path: "当前特性/payment-settlement",
      system_role: "feature_space_current",
      sort_order: 0,
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
    },
    {
      id: 701,
      space_id: 70,
      feature_id: 7,
      parent_id: -100007,
      type: "folder",
      name: "知识库",
      path: "knowledge-base",
      system_role: "knowledge_base",
      sort_order: 100,
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
    },
    ...importedNodes,
  ];
}

function wikiDocumentNode(id: number, name: string, nodePath: string) {
  return {
    id,
    space_id: 70,
    feature_id: 7,
    parent_id: 701,
    type: "document",
    name,
    path: nodePath,
    system_role: null,
    sort_order: 0,
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
  };
}

function buildDocumentDetail(nodeId: number, title: string, body: string) {
  return {
    document_id: nodeId + 1000,
    node_id: nodeId,
    title,
    current_version_id: nodeId + 2000,
    current_body_markdown: body,
    draft_body_markdown: null,
    index_status: "ready",
    broken_refs_json: {
      links: [],
      assets: [],
    },
    resolved_refs_json: [],
    provenance_json: null,
    permissions: {
      read: true,
      write: true,
      admin: true,
    },
  };
}

function buildDocumentVersions(nodeId: number) {
  return {
    versions: [
      {
        id: nodeId + 2000,
        document_id: nodeId + 1000,
        version_no: 1,
        body_markdown: "# version",
        created_by_subject_id: "client_e2e",
        created_at: "2026-04-30T10:00:00",
        updated_at: "2026-04-30T10:00:00",
      },
    ],
  };
}

function buildDirectorySessionSummary(
  stage: "initial" | "after_first_failure" | "after_second_uploaded",
) {
  if (stage === "after_second_uploaded") {
    return {
      id: 431,
      space_id: 70,
      parent_id: 701,
      mode: "directory",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 3,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 1,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 1,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_first_failure") {
    return {
      id: 431,
      space_id: 70,
      parent_id: 701,
      mode: "directory",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 3,
        pending_count: 1,
        uploading_count: 0,
        uploaded_count: 0,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 1,
        skipped_count: 0,
      },
    };
  }
  return {
    id: 431,
    space_id: 70,
    parent_id: 701,
    mode: "directory",
    status: "running",
    requested_by_subject_id: "client_e2e",
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
    summary: {
      total_files: 3,
      pending_count: 2,
      uploading_count: 0,
      uploaded_count: 0,
      conflict_count: 0,
      failed_count: 0,
      ignored_count: 1,
      skipped_count: 0,
    },
  };
}

function buildDirectoryItems(stage: "initial" | "after_first_failure" | "after_second_uploaded") {
  return [
    {
      id: 1,
      source_path: "ops/Guide.md",
      target_path: "knowledge-base/guide",
      item_kind: "document",
      status: stage === "initial" ? "pending" : "failed",
      progress_percent: stage === "initial" ? 0 : 100,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_431/ops/Guide.md",
      result_node_id: null,
      error_message: stage === "initial" ? null : "first upload failed",
    },
    {
      id: 2,
      source_path: "ops/images/logo.png",
      target_path: "knowledge-base/images/logo.png",
      item_kind: "asset",
      status: stage === "after_second_uploaded" ? "uploaded" : "pending",
      progress_percent: stage === "after_second_uploaded" ? 100 : 0,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_431/ops/images/logo.png",
      result_node_id: stage === "after_second_uploaded" ? 711 : null,
      error_message: null,
    },
    {
      id: 3,
      source_path: "ops/raw/trace.log",
      target_path: null,
      item_kind: "ignored",
      status: "ignored",
      progress_percent: 0,
      ignore_reason: "not_referenced",
      staging_path: null,
      result_node_id: null,
      error_message: null,
    },
  ];
}

function buildConflictSessionSummary(
  stage: "initial" | "after_first_conflict" | "after_second_uploaded" | "completed",
) {
  if (stage === "completed") {
    return {
      id: 432,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "completed",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 2,
        conflict_count: 0,
        failed_count: 0,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_second_uploaded") {
    return {
      id: 432,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 1,
        conflict_count: 1,
        failed_count: 0,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_first_conflict") {
    return {
      id: 432,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 1,
        uploading_count: 0,
        uploaded_count: 0,
        conflict_count: 1,
        failed_count: 0,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  return {
    id: 432,
    space_id: 70,
    parent_id: 701,
    mode: "markdown",
    status: "running",
    requested_by_subject_id: "client_e2e",
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
    summary: {
      total_files: 2,
      pending_count: 2,
      uploading_count: 0,
      uploaded_count: 0,
      conflict_count: 0,
      failed_count: 0,
      ignored_count: 0,
      skipped_count: 0,
    },
  };
}

function buildConflictItems(
  stage: "initial" | "after_first_conflict" | "after_second_uploaded" | "completed",
) {
  return [
    {
      id: 1,
      source_path: "Runbook.md",
      target_path: "knowledge-base/runbook",
      item_kind: "document",
      status: stage === "initial" ? "pending" : stage === "completed" ? "uploaded" : "conflict",
      progress_percent: stage === "initial" ? 0 : 100,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_432/Runbook.md",
      result_node_id: stage === "completed" ? 707 : null,
      error_message:
        stage === "initial" || stage === "completed"
          ? null
          : "wiki node path conflict: knowledge-base/runbook",
    },
    {
      id: 2,
      source_path: "Guide.md",
      target_path: "knowledge-base/guide",
      item_kind: "document",
      status: stage === "after_second_uploaded" || stage === "completed" ? "uploaded" : "pending",
      progress_percent: stage === "after_second_uploaded" || stage === "completed" ? 100 : 0,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_432/Guide.md",
      result_node_id: stage === "after_second_uploaded" || stage === "completed" ? 708 : null,
      error_message: null,
    },
  ];
}

function buildRetrySessionSummary(
  stage: "initial" | "after_first_failure" | "after_second_uploaded" | "completed",
) {
  if (stage === "completed") {
    return {
      id: 433,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "completed",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 2,
        conflict_count: 0,
        failed_count: 0,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_second_uploaded") {
    return {
      id: 433,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 0,
        uploading_count: 0,
        uploaded_count: 1,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  if (stage === "after_first_failure") {
    return {
      id: 433,
      space_id: 70,
      parent_id: 701,
      mode: "markdown",
      status: "running",
      requested_by_subject_id: "client_e2e",
      created_at: "2026-04-30T10:00:00",
      updated_at: "2026-04-30T10:00:00",
      summary: {
        total_files: 2,
        pending_count: 1,
        uploading_count: 0,
        uploaded_count: 0,
        conflict_count: 0,
        failed_count: 1,
        ignored_count: 0,
        skipped_count: 0,
      },
    };
  }
  return {
    id: 433,
    space_id: 70,
    parent_id: 701,
    mode: "markdown",
    status: "running",
    requested_by_subject_id: "client_e2e",
    created_at: "2026-04-30T10:00:00",
    updated_at: "2026-04-30T10:00:00",
    summary: {
      total_files: 2,
      pending_count: 2,
      uploading_count: 0,
      uploaded_count: 0,
      conflict_count: 0,
      failed_count: 0,
      ignored_count: 0,
      skipped_count: 0,
    },
  };
}

function buildRetryItems(
  stage: "initial" | "after_first_failure" | "after_second_uploaded" | "completed",
) {
  return [
    {
      id: 1,
      source_path: "Runbook.md",
      target_path: "knowledge-base/runbook",
      item_kind: "document",
      status: stage === "initial" ? "pending" : stage === "completed" ? "uploaded" : "failed",
      progress_percent: stage === "initial" ? 0 : 100,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_433/Runbook.md",
      result_node_id: stage === "completed" ? 709 : null,
      error_message: stage === "initial" || stage === "completed" ? null : "first upload failed",
    },
    {
      id: 2,
      source_path: "Guide.md",
      target_path: "knowledge-base/guide",
      item_kind: "document",
      status: stage === "after_second_uploaded" || stage === "completed" ? "uploaded" : "pending",
      progress_percent: stage === "after_second_uploaded" || stage === "completed" ? 100 : 0,
      ignore_reason: null,
      staging_path: "/tmp/wiki/imports/session_433/Guide.md",
      result_node_id: stage === "after_second_uploaded" || stage === "completed" ? 710 : null,
      error_message: null,
    },
  ];
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
