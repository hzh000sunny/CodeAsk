import { mkdir, mkdtemp } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.dirname(e2eDir);
const repoRoot = path.dirname(frontendRoot);

export async function makeCodeAskE2eTempDir(prefix: string): Promise<string> {
  const root = process.env.CODEASK_TEST_TMPDIR || path.join(repoRoot, ".tmp", "playwright");
  await mkdir(root, { recursive: true });
  return mkdtemp(path.join(root, prefix));
}
