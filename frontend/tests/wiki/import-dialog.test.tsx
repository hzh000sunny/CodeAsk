import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WikiImportDialog } from "../../src/components/wiki/WikiImportDialog";
import type {
  WikiImportSessionItemsRead,
  WikiImportSessionRead,
} from "../../src/types/wiki";

function buildSession(overrides?: Partial<WikiImportSessionRead>): WikiImportSessionRead {
  return {
    id: 11,
    space_id: 7,
    parent_id: 101,
    mode: "directory",
    status: "running",
    requested_by_subject_id: "client_test",
    created_at: "2026-05-05T10:00:00Z",
    updated_at: "2026-05-05T10:00:00Z",
    summary: {
      total_files: 2,
      pending_count: 1,
      uploading_count: 0,
      uploaded_count: 0,
      conflict_count: 0,
      failed_count: 0,
      ignored_count: 1,
      skipped_count: 0,
    },
    ...overrides,
  };
}

function buildSessionItems(overrides?: Partial<WikiImportSessionItemsRead>): WikiImportSessionItemsRead {
  return {
    items: [
      {
        id: 1,
        source_path: "ops/Guide.md",
        target_path: "knowledge-base/guide",
        item_kind: "document",
        status: "pending",
        progress_percent: 0,
        ignore_reason: null,
        staging_path: null,
        result_node_id: null,
      },
      {
        id: 2,
        source_path: "ops/raw/trace.log",
        target_path: null,
        item_kind: "ignored",
        status: "ignored",
        progress_percent: 0,
        ignore_reason: "not_referenced",
        staging_path: null,
        result_node_id: null,
      },
    ],
    ...overrides,
  };
}

describe("WikiImportDialog", () => {
  it("renders the compact workbench intro for option A without extra helper copy", () => {
    const { container } = render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession()}
        sessionItems={buildSessionItems()}
      />,
    );

    expect(
      screen.queryByText("支持 Markdown、目录导入、相对资源和内部链接。"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("导入后自动索引")).not.toBeInTheDocument();
    expect(screen.queryByText("图片自动保留")).not.toBeInTheDocument();
    expect(screen.getByText("导入 Markdown")).toBeInTheDocument();
    expect(screen.getByText("导入目录")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "导入队列" })).toBeInTheDocument();
    expect(container.querySelector(".wiki-import-picker-grid.wiki-import-picker-grid-compact")).not.toBeNull();
    expect(container.querySelector('.wiki-import-section[data-empty="false"]')).not.toBeNull();
  });

  it("marks the queue container as empty before files are selected", () => {
    const { container } = render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={null}
        sessionItems={null}
      />,
    );

    expect(container.querySelector('.wiki-import-section[data-empty="true"]')).not.toBeNull();
  });

  it("supports picking markdown files and directories and returns full queue items", async () => {
    const onFilesSelected = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={onFilesSelected}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={null}
        sessionItems={null}
      />,
    );

    const markdownFile = new File(["# Runbook"], "Runbook.md", {
      type: "text/markdown",
    });
    fireEvent.change(screen.getByLabelText("选择 Markdown 文件"), {
      target: { files: [markdownFile] },
    });
    await waitFor(() => {
      expect(onFilesSelected).toHaveBeenCalledWith({
        files: [markdownFile],
        items: [
          {
            file: markdownFile,
            relativePath: "Runbook.md",
            itemKind: "document",
            included: true,
            ignoreReason: null,
          },
        ],
        mode: "markdown",
      });
    });
    expect(await screen.findByText("已选择 Markdown：Runbook.md")).toBeInTheDocument();

    const directoryFile = new File(["# Guide"], "Guide.md", {
      type: "text/markdown",
    });
    Object.defineProperty(directoryFile, "webkitRelativePath", {
      configurable: true,
      value: "ops/Guide.md",
    });
    fireEvent.change(screen.getByLabelText("选择 Wiki 目录"), {
      target: { files: [directoryFile] },
    });
    await waitFor(() => {
      expect(onFilesSelected).toHaveBeenLastCalledWith({
        files: [directoryFile],
        items: [
          {
            file: directoryFile,
            relativePath: "ops/Guide.md",
            itemKind: "document",
            included: true,
            ignoreReason: null,
          },
        ],
        mode: "directory",
      });
    });
    expect(await screen.findByText("已选择目录 ops（1 个可导入文件）")).toBeInTheDocument();
  });

  it("renders queue summary and keeps ignored files collapsed by default", async () => {
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession()}
        sessionItems={buildSessionItems()}
      />,
    );

    expect(screen.getByText("目标目录 knowledge-base")).toBeInTheDocument();
    expect(screen.getByText("待上传 1")).toBeInTheDocument();
    expect(screen.getByText("已忽略 1")).toBeInTheDocument();
    expect(screen.getByText("ops/Guide.md")).toBeInTheDocument();
    expect(screen.getByText("知识库 / guide")).toBeInTheDocument();
    expect(screen.queryByText("ops/raw/trace.log")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "已忽略 1" }));
    expect(await screen.findByText("ops/raw/trace.log")).toBeInTheDocument();
  });

  it("opens ignored files directly from the top summary badge", async () => {
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession()}
        sessionItems={buildSessionItems()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "已忽略 1" }));

    expect(await screen.findByText("ops/raw/trace.log")).toBeInTheDocument();
    expect(screen.queryByText("ops/Guide.md")).not.toBeInTheDocument();
  });

  it("filters the queue when clicking other top summary badges", async () => {
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession({
          summary: {
            total_files: 3,
            pending_count: 1,
            uploading_count: 0,
            uploaded_count: 1,
            conflict_count: 0,
            failed_count: 0,
            ignored_count: 1,
            skipped_count: 0,
          },
        })}
        sessionItems={{
          items: [
            {
              id: 1,
              source_path: "ops/Guide.md",
              target_path: "knowledge-base/guide",
              item_kind: "document",
              status: "pending",
              progress_percent: 0,
              ignore_reason: null,
              staging_path: null,
              result_node_id: null,
            },
            {
              id: 2,
              source_path: "ops/Done.md",
              target_path: "knowledge-base/done",
              item_kind: "document",
              status: "uploaded",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Done.md",
              result_node_id: 99,
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
            },
          ],
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "已上传 1" }));

    expect(await screen.findByText("ops/Done.md")).toBeInTheDocument();
    expect(screen.queryByText("ops/Guide.md")).not.toBeInTheDocument();
    expect(screen.queryByText("ops/raw/trace.log")).not.toBeInTheDocument();
  });

  it("lets users expand ignored files immediately after local selection", async () => {
    const onFilesSelected = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={onFilesSelected}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={null}
        sessionItems={null}
      />,
    );

    const markdownFile = new File(["# Guide"], "Guide.md", {
      type: "text/markdown",
    });
    Object.defineProperty(markdownFile, "webkitRelativePath", {
      configurable: true,
      value: "ops/Guide.md",
    });
    const ignoredFile = new File(["trace"], "trace.log", {
      type: "text/plain",
    });
    Object.defineProperty(ignoredFile, "webkitRelativePath", {
      configurable: true,
      value: "ops/raw/trace.log",
    });

    fireEvent.change(screen.getByLabelText("选择 Wiki 目录"), {
      target: { files: [markdownFile, ignoredFile] },
    });

    expect(
      await screen.findByText("已忽略 1 个非 Wiki 文件，仅保留 Markdown 和被 Markdown 引用的静态资源。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("ops/raw/trace.log")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "已忽略 1 个文件" }));

    expect(await screen.findByText("ops/raw/trace.log")).toBeInTheDocument();
    expect(await screen.findByText("not_referenced")).toBeInTheDocument();
    expect(onFilesSelected).toHaveBeenCalledTimes(1);
  });

  it("shows a visible pending banner while queue is being prepared", async () => {
    const onFilesSelected = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={onFilesSelected}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending
        session={null}
        sessionItems={null}
      />,
    );

    const directoryFile = new File(["# Guide"], "Guide.md", {
      type: "text/markdown",
    });
    Object.defineProperty(directoryFile, "webkitRelativePath", {
      configurable: true,
      value: "ops/Guide.md",
    });
    fireEvent.change(screen.getByLabelText("选择 Wiki 目录"), {
      target: { files: [directoryFile] },
    });

    expect(await screen.findByText("正在准备导入队列…")).toBeInTheDocument();
  });

  it("shows aggregate progress and current processing file in the summary area", async () => {
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession({
          summary: {
            total_files: 4,
            pending_count: 0,
            uploading_count: 1,
            uploaded_count: 1,
            conflict_count: 0,
            failed_count: 0,
            ignored_count: 1,
            skipped_count: 1,
          },
        })}
        sessionItems={{
          items: [
            {
              id: 1,
              source_path: "ops/Guide.md",
              target_path: "knowledge-base/guide",
              item_kind: "document",
              status: "uploaded",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Guide.md",
              result_node_id: 101,
            },
            {
              id: 2,
              source_path: "ops/Runbook.md",
              target_path: "knowledge-base/runbook",
              item_kind: "document",
              status: "uploading",
              progress_percent: 45,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Runbook.md",
              result_node_id: null,
            },
            {
              id: 3,
              source_path: "ops/trace.log",
              target_path: null,
              item_kind: "ignored",
              status: "ignored",
              progress_percent: 0,
              ignore_reason: "not_referenced",
              staging_path: null,
              result_node_id: null,
            },
            {
              id: 4,
              source_path: "ops/legacy.md",
              target_path: "knowledge-base/legacy",
              item_kind: "document",
              status: "skipped",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/legacy.md",
              result_node_id: null,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("总进度 82%")).toBeInTheDocument();
    expect(screen.getByText("当前处理 ops/Runbook.md")).toBeInTheDocument();
  });

  it("filters the queue down to active work while keeping ignored files separate", async () => {
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession({
          summary: {
            total_files: 5,
            pending_count: 1,
            uploading_count: 1,
            uploaded_count: 1,
            conflict_count: 0,
            failed_count: 1,
            ignored_count: 1,
            skipped_count: 1,
          },
        })}
        sessionItems={{
          items: [
            {
              id: 1,
              source_path: "ops/Guide.md",
              target_path: "knowledge-base/guide",
              item_kind: "document",
              status: "uploaded",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Guide.md",
              result_node_id: 101,
            },
            {
              id: 2,
              source_path: "ops/Runbook.md",
              target_path: "knowledge-base/runbook",
              item_kind: "document",
              status: "uploading",
              progress_percent: 45,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Runbook.md",
              result_node_id: null,
            },
            {
              id: 3,
              source_path: "ops/Error.md",
              target_path: "knowledge-base/error",
              item_kind: "document",
              status: "failed",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Error.md",
              result_node_id: null,
            },
            {
              id: 4,
              source_path: "ops/Todo.md",
              target_path: "knowledge-base/todo",
              item_kind: "document",
              status: "pending",
              progress_percent: 0,
              ignore_reason: null,
              staging_path: null,
              result_node_id: null,
            },
            {
              id: 5,
              source_path: "ops/legacy.md",
              target_path: "knowledge-base/legacy",
              item_kind: "document",
              status: "skipped",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/legacy.md",
              result_node_id: null,
            },
            {
              id: 6,
              source_path: "ops/trace.log",
              target_path: null,
              item_kind: "ignored",
              status: "ignored",
              progress_percent: 0,
              ignore_reason: "not_referenced",
              staging_path: null,
              result_node_id: null,
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("ops/Guide.md")).toBeInTheDocument();
    expect(screen.getByText("ops/legacy.md")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /仅看进行中与失败/ }));

    expect(screen.queryByText("ops/Guide.md")).not.toBeInTheDocument();
    expect(screen.queryByText("ops/legacy.md")).not.toBeInTheDocument();
    expect(screen.getByText("ops/Runbook.md")).toBeInTheDocument();
    expect(screen.getByText("ops/Error.md")).toBeInTheDocument();
    expect(screen.getByText("ops/Todo.md")).toBeInTheDocument();
    expect(screen.queryByText("ops/trace.log")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "已忽略 1" }));
    expect(await screen.findByText("ops/trace.log")).toBeInTheDocument();
  });

  it("renders conflict actions and dispatches row and bulk resolve handlers", async () => {
    const onResolveItem = vi.fn();
    const onBulkResolve = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={onBulkResolve}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={onResolveItem}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession({
          summary: {
            total_files: 1,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 0,
            conflict_count: 1,
            failed_count: 0,
            ignored_count: 0,
            skipped_count: 0,
          },
        })}
        sessionItems={{
          items: [
            {
              id: 9,
              source_path: "ops/Runbook.md",
              target_path: "knowledge-base/runbook",
              item_kind: "document",
              status: "conflict",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Runbook.md",
              result_node_id: null,
              error_message: "wiki node path conflict: knowledge-base/runbook",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("wiki node path conflict: 知识库 / runbook")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "覆盖" }));
    expect(onResolveItem).toHaveBeenCalledWith(9, "overwrite");

    fireEvent.click(screen.getByRole("button", { name: "跳过" }));
    expect(onResolveItem).toHaveBeenCalledWith(9, "skip");

    fireEvent.click(screen.getByRole("button", { name: "全部覆盖" }));
    expect(onBulkResolve).toHaveBeenCalledWith("overwrite_all");

    fireEvent.click(screen.getByRole("button", { name: "全部跳过" }));
    expect(onBulkResolve).toHaveBeenCalledWith("skip_all");
  });

  it("asks for confirmation before closing an unfinished import session", async () => {
    const onClose = vi.fn();
    const onContinueInBackground = vi.fn();
    const onCancelImport = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={onCancelImport}
        onClose={onClose}
        onContinueInBackground={onContinueInBackground}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={vi.fn()}
        onRetryItem={vi.fn()}
        open
        pending={false}
        session={buildSession()}
        sessionItems={buildSessionItems()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    expect(await screen.findByText("导入尚未完成")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "继续后台" }));
    expect(onContinueInBackground).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(screen.getByRole("button", { name: "取消上传" }));
    expect(onCancelImport).toHaveBeenCalledTimes(1);
  });

  it("renders failed retry actions and dispatches row and bulk retry handlers", async () => {
    const onRetryItem = vi.fn();
    const onRetryFailed = vi.fn();
    render(
      <WikiImportDialog
        actionPendingKey={null}
        errorMessage=""
        hasUnfinishedSession={false}
        importTargetLabel="knowledge-base"
        onBulkResolve={vi.fn()}
        onCancelImport={vi.fn()}
        onClose={vi.fn()}
        onContinueInBackground={vi.fn()}
        onFilesSelected={vi.fn()}
        onResolveItem={vi.fn()}
        onRetryFailed={onRetryFailed}
        onRetryItem={onRetryItem}
        open
        pending={false}
        session={buildSession({
          summary: {
            total_files: 2,
            pending_count: 0,
            uploading_count: 0,
            uploaded_count: 0,
            conflict_count: 0,
            failed_count: 2,
            ignored_count: 0,
            skipped_count: 0,
          },
        })}
        sessionItems={{
          items: [
            {
              id: 21,
              source_path: "ops/Runbook.md",
              target_path: "knowledge-base/runbook",
              item_kind: "document",
              status: "failed",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Runbook.md",
              result_node_id: null,
              error_message: "staged import file missing: ops/Runbook.md",
            },
            {
              id: 22,
              source_path: "ops/Guide.md",
              target_path: "knowledge-base/guide",
              item_kind: "document",
              status: "failed",
              progress_percent: 100,
              ignore_reason: null,
              staging_path: "/tmp/wiki/imports/session_11/ops/Guide.md",
              result_node_id: null,
              error_message: "staged import file missing: ops/Guide.md",
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByText("staged import file missing: ops/Runbook.md"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "重试" })[0]);
    expect(onRetryItem).toHaveBeenCalledWith(21);

    fireEvent.click(screen.getByRole("button", { name: "重试失败项" }));
    expect(onRetryFailed).toHaveBeenCalledWith();
  });
});
