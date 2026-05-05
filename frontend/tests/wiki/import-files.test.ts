import { describe, expect, it } from "vitest";

import { filterWikiImportFiles } from "../../src/lib/wiki/import-files";

function directoryFile(path: string, type = "text/plain", content = "content") {
  const name = path.split("/").at(-1) ?? path;
  const file = new File([content], name, { type });
  Object.defineProperty(file, "webkitRelativePath", {
    configurable: true,
    value: path,
  });
  return file;
}

describe("filterWikiImportFiles", () => {
  it("keeps markdown and only assets referenced by markdown for directory imports", async () => {
    const result = await filterWikiImportFiles(
      [
        directoryFile(
          "docs/Guide.md",
          "text/markdown",
          "# Guide\n\n![Logo](./images/logo.png)\n[Spec](./appendix.md)",
        ),
        directoryFile("docs/images/logo.png", "image/png"),
        directoryFile("docs/images/unused.png", "image/png"),
        directoryFile("docs/files/report.pdf", "application/pdf"),
        directoryFile("docs/src/index.ts", "text/plain"),
        directoryFile("docs/package.json", "application/json"),
      ],
      "directory",
    );

    expect(
      result.items.map((item) => ({
        path: item.relativePath,
        included: item.included,
        kind: item.itemKind,
      })),
    ).toEqual([
      { path: "docs/Guide.md", included: true, kind: "document" },
      { path: "docs/images/logo.png", included: true, kind: "asset" },
      { path: "docs/images/unused.png", included: false, kind: "ignored" },
      { path: "docs/files/report.pdf", included: false, kind: "ignored" },
      { path: "docs/src/index.ts", included: false, kind: "ignored" },
      { path: "docs/package.json", included: false, kind: "ignored" },
    ]);
    expect(result.accepted.map((file) => file.webkitRelativePath || file.name)).toEqual([
      "docs/Guide.md",
      "docs/images/logo.png",
    ]);
    expect(result.skippedCount).toBe(4);
  });

  it("keeps only markdown files for markdown uploads", async () => {
    const result = await filterWikiImportFiles(
      [
        directoryFile("Runbook.md", "text/markdown"),
        directoryFile("diagram.png", "image/png"),
      ],
      "markdown",
    );

    expect(
      result.items.map((item) => ({
        path: item.relativePath,
        included: item.included,
        kind: item.itemKind,
      })),
    ).toEqual([
      { path: "Runbook.md", included: true, kind: "document" },
      { path: "diagram.png", included: false, kind: "ignored" },
    ]);
    expect(result.accepted.map((file) => file.name)).toEqual(["Runbook.md"]);
    expect(result.skippedCount).toBe(1);
  });

  it("includes referenced sibling assets from nested markdown files", async () => {
    const guide = directoryFile(
      "kb/guides/Guide.md",
      "text/markdown",
      "# Guide\n\n![Diagram](../images/diagram.png)\n",
    );
    const diagram = directoryFile("kb/images/diagram.png", "image/png");

    const result = await filterWikiImportFiles(
      [guide, diagram, directoryFile("kb/images/unused.png", "image/png")],
      "directory",
    );

    expect(result.accepted.map((file) => file.webkitRelativePath || file.name)).toEqual([
      "kb/guides/Guide.md",
      "kb/images/diagram.png",
    ]);
    expect(result.skippedCount).toBe(1);
  });

  it("ignores external links and only includes local referenced assets", async () => {
    const guide = directoryFile(
      "kb/Guide.md",
      "text/markdown",
      '# Guide\n\n![Logo](https://example.com/logo.png)\n[Image](./images/local.png)\n',
    );

    const result = await filterWikiImportFiles(
      [guide, directoryFile("kb/images/local.png", "image/png")],
      "directory",
    );

    expect(result.accepted.map((file) => file.webkitRelativePath || file.name)).toEqual([
      "kb/Guide.md",
      "kb/images/local.png",
    ]);
  });

  it("keeps assets referenced by html img tags inside markdown files", async () => {
    const guide = directoryFile(
      "kb/小米病历.md",
      "text/markdown",
      '<img src="Untitled.assets/image-20251217001114824.png" alt="image" style="zoom:50%;" />\n',
    );

    const result = await filterWikiImportFiles(
      [
        guide,
        directoryFile("kb/Untitled.assets/image-20251217001114824.png", "image/png"),
        directoryFile("kb/Untitled.assets/unused.png", "image/png"),
      ],
      "directory",
    );

    expect(result.accepted.map((file) => file.webkitRelativePath || file.name)).toEqual([
      "kb/小米病历.md",
      "kb/Untitled.assets/image-20251217001114824.png",
    ]);
    expect(result.skippedCount).toBe(1);
  });
});
