import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";

export type GitCheckoutSetupResult = {
  gitDir: string;
  initialized: boolean;
  skipped: boolean;
};

export function ensureReferenceGitCheckout(fixturePath: string): GitCheckoutSetupResult {
  const gitDir = `${fixturePath}/.git`;
  if (!existsSync(fixturePath)) {
    return { gitDir, initialized: false, skipped: true };
  }
  if (existsSync(gitDir)) {
    return { gitDir, initialized: false, skipped: false };
  }

  runGit(fixturePath, ["init"]);
  runGit(fixturePath, ["add", "-A"]);
  runGit(fixturePath, [
    "-c",
    "user.email=e2e@codeask",
    "-c",
    "user.name=e2e",
    "commit",
    "-m",
    "e2e fixture snapshot",
  ]);
  return { gitDir, initialized: true, skipped: false };
}

function runGit(cwd: string, args: string[]) {
  execFileSync("git", args, {
    cwd,
    env: { ...process.env, GIT_CONFIG_NOSYSTEM: "1" },
    stdio: "ignore",
  });
}
