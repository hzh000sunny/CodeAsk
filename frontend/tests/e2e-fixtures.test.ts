import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { ensureReferenceGitCheckout } from "../e2e/setup-fixtures";

describe("ensureReferenceGitCheckout", () => {
  it("initializes a git snapshot for an existing fixture without .git", () => {
      const root = mkdtempSync(path.join(tmpdir(), "codeask-e2e-fixture-"));
      try {
        const fixture = path.join(root, "anything-llm");
        mkdirSync(fixture);
        writeFileSync(path.join(root, ".keep"), "root\n", "utf-8");
      writeFileSync(path.join(root, "outside.txt"), "outside\n", "utf-8");
      writeFileSync(path.join(fixture, "README.md"), "# fixture\n", {
        encoding: "utf-8",
        flag: "wx",
      });

      const result = ensureReferenceGitCheckout(fixture);

      expect(result.initialized).toBe(true);
      expect(result.skipped).toBe(false);
      expect(result.gitDir).toBe(path.join(fixture, ".git"));

      const secondResult = ensureReferenceGitCheckout(fixture);
      expect(secondResult.initialized).toBe(false);
      expect(secondResult.skipped).toBe(false);
      expect(secondResult.gitDir).toBe(path.join(fixture, ".git"));
    } finally {
      rmSync(root, { force: true, recursive: true });
    }
  });
});
