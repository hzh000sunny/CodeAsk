import type { WikiImportSelectionItem } from "../../types/wiki";

const MARKDOWN_EXTENSIONS = new Set([".md", ".markdown"]);
const STATIC_ASSET_EXTENSIONS = new Set([
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".bmp",
  ".ico",
  ".avif",
]);

const IMAGE_LINK_RE = /!\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const REL_LINK_RE = /(?<!!)\[[^\]]+\]\(([^)\s#]+)(?:\s+"[^"]*")?\)/g;
const HTML_IMAGE_SRC_RE = /<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;

export async function filterWikiImportFiles(
  files: File[],
  mode: "markdown" | "directory",
): Promise<{
  accepted: File[];
  items: WikiImportSelectionItem[];
  skippedCount: number;
}> {
  const markdownFiles = files.filter((file) =>
    MARKDOWN_EXTENSIONS.has(fileExtension(file.webkitRelativePath || file.name)),
  );

  if (mode === "markdown") {
    const acceptedPaths = new Set(markdownFiles.map((file) => file.webkitRelativePath || file.name));
    return {
      accepted: markdownFiles,
      items: [
        ...files
          .filter((file) => acceptedPaths.has(file.webkitRelativePath || file.name))
          .map((file) => ({
            file,
            relativePath: file.webkitRelativePath || file.name,
            itemKind: "document" as const,
            included: true,
            ignoreReason: null,
          })),
        ...files
          .filter((file) => !acceptedPaths.has(file.webkitRelativePath || file.name))
          .map((file) => ({
            file,
            relativePath: file.webkitRelativePath || file.name,
            itemKind: "ignored" as const,
            included: false,
            ignoreReason: "unsupported" as const,
          })),
      ],
      skippedCount: files.length - markdownFiles.length,
    };
  }

  const byPath = new Map<string, File>();
  for (const file of files) {
    byPath.set(file.webkitRelativePath || file.name, file);
  }

  const referencedAssetPaths = new Set<string>();
  for (const markdownFile of markdownFiles) {
    const currentPath = markdownFile.webkitRelativePath || markdownFile.name;
    const body = await readFileText(markdownFile);
    for (const target of parseMarkdownTargets(body)) {
      const resolvedPath = resolveReferenceWithinImportRoot(currentPath, target);
      if (!resolvedPath) {
        continue;
      }
      if (!STATIC_ASSET_EXTENSIONS.has(fileExtension(resolvedPath))) {
        continue;
      }
      if (byPath.has(resolvedPath)) {
        referencedAssetPaths.add(resolvedPath);
      }
    }
  }

  const accepted = files.filter((file) => {
    const path = file.webkitRelativePath || file.name;
    if (MARKDOWN_EXTENSIONS.has(fileExtension(path))) {
      return true;
    }
    return referencedAssetPaths.has(path);
  });
  const acceptedPaths = new Set(accepted.map((file) => file.webkitRelativePath || file.name));

  return {
    accepted,
    items: [
      ...files
        .filter((file) => acceptedPaths.has(file.webkitRelativePath || file.name))
        .map((file) => {
          const relativePath = file.webkitRelativePath || file.name;
          const extension = fileExtension(relativePath);
          return {
            file,
            relativePath,
            itemKind: MARKDOWN_EXTENSIONS.has(extension) ? ("document" as const) : ("asset" as const),
            included: true,
            ignoreReason: null,
          };
        }),
      ...files
        .filter((file) => !acceptedPaths.has(file.webkitRelativePath || file.name))
        .map((file) => ({
          file,
          relativePath: file.webkitRelativePath || file.name,
          itemKind: "ignored" as const,
          included: false,
          ignoreReason: referencedAssetPaths.has(file.webkitRelativePath || file.name)
            ? null
            : ("not_referenced" as const),
        })),
    ],
    skippedCount: files.length - accepted.length,
  };
}

function parseMarkdownTargets(source: string): string[] {
  const targets: string[] = [];
  const seen = new Set<string>();
  for (const regex of [IMAGE_LINK_RE, REL_LINK_RE, HTML_IMAGE_SRC_RE]) {
    regex.lastIndex = 0;
    for (const match of source.matchAll(regex)) {
      const target = match[1];
      if (!target || seen.has(target) || isExternalTarget(target)) {
        continue;
      }
      seen.add(target);
      targets.push(target);
    }
  }
  return targets;
}

function resolveReferenceWithinImportRoot(
  sourcePath: string,
  target: string,
): string | null {
  const cleanedTarget = target.split("#", 1)[0]?.split("?", 1)[0] ?? "";
  if (!cleanedTarget) {
    return null;
  }

  const sourceParts = sourcePath.split("/").filter(Boolean);
  if (sourceParts.length === 0) {
    return null;
  }
  const root = sourceParts[0];
  const baseParts = cleanedTarget.startsWith("/")
    ? [root]
    : sourceParts.slice(0, -1);
  const targetParts = cleanedTarget.split("/").filter(Boolean);

  const normalized: string[] = [...baseParts];
  for (const part of targetParts) {
    if (part === ".") {
      continue;
    }
    if (part === "..") {
      if (normalized.length > 1) {
        normalized.pop();
      }
      continue;
    }
    normalized.push(part);
  }

  return normalized.join("/");
}

function fileExtension(path: string): string {
  const normalized = path.toLowerCase();
  const dotIndex = normalized.lastIndexOf(".");
  return dotIndex >= 0 ? normalized.slice(dotIndex) : "";
}

function isExternalTarget(target: string): boolean {
  return (
    target.startsWith("#") ||
    /^[a-z][a-z0-9+.-]*:/i.test(target)
  );
}

async function readFileText(file: File): Promise<string> {
  if (typeof file.text === "function") {
    return file.text();
  }

  if (typeof FileReader !== "undefined") {
    return new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        resolve(typeof reader.result === "string" ? reader.result : "");
      };
      reader.onerror = () => {
        reject(reader.error ?? new Error("Unable to read file content."));
      };
      reader.readAsText(file);
    });
  }

  if (typeof Response !== "undefined") {
    return new Response(file).text();
  }

  return String(file);
}
