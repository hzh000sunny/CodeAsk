import path from "node:path";
import { fileURLToPath } from "node:url";

import { ensureReferenceGitCheckout } from "./setup-fixtures";

export default function globalSetup() {
  const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const repoRoot = path.resolve(frontendDir, "..");
  ensureReferenceGitCheckout(path.join(repoRoot, "references", "anything-llm"));
}
