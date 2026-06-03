import { expect, type Page, test } from "@playwright/test";

const ADMIN_USERNAME = process.env.CODEASK_E2E_ADMIN_USERNAME ?? "admin";
const ADMIN_PASSWORD = process.env.CODEASK_E2E_ADMIN_PASSWORD ?? "admin";

test.describe("OpenCode tool permissions", () => {
  test("admin configures a bash whitelist and it persists across reload", async ({ page }) => {
    await loginAdmin(page);
    await openOpencodeConsole(page);

    // The OpenCode page exposes both the status console and the permission matrix.
    await expect(page.getByRole("region", { name: "opencode 后端状态" })).toBeVisible();
    const perms = page.getByRole("region", { name: "opencode 工具权限" });
    await expect(perms).toBeVisible();

    // Save is disabled until something changes.
    const save = perms.getByRole("button", { name: "保存" });
    await expect(save).toBeDisabled();

    // Switch bash to whitelist mode -> the terminal allowlist editor appears.
    const bashRow = perms.locator(".opencode-bash-row");
    await bashRow.getByRole("radio", { name: "白名单" }).click();
    const terminal = perms.getByLabel("bash 命令白名单");
    await expect(terminal).toBeVisible();

    // Quick-fill recommended commands, then add a custom pattern.
    await terminal.getByRole("button", { name: /填入推荐/ }).click();
    await expect(terminal.getByText("git status")).toBeVisible();
    await terminal.getByLabel("添加命令通配符").fill("rg *");
    await terminal.getByRole("button", { name: "添加" }).click();
    await expect(terminal.getByText("rg *")).toBeVisible();

    // Save through the confirmation dialog.
    await expect(save).toBeEnabled();
    await save.click();
    await page.getByRole("button", { name: "确认保存" }).click();
    await expect(page.getByText("工具权限已保存，对新建会话生效")).toBeVisible();

    // The backend persisted a bash object permission with the patterns.
    const stored = await page.request.get("/api/admin/opencode/permissions");
    expect(stored.ok()).toBeTruthy();
    const body = await stored.json();
    expect(body.bash.mode).toBe("whitelist");
    expect(body.bash.patterns).toContain("git status");
    expect(body.bash.patterns).toContain("rg *");

    // Reload: whitelist mode and patterns survive.
    await page.reload({ waitUntil: "domcontentloaded" });
    const permsAfter = page.getByRole("region", { name: "opencode 工具权限" });
    await expect(
      permsAfter.locator(".opencode-bash-row").getByRole("radio", { name: "白名单" }),
    ).toHaveAttribute("aria-checked", "true");
    await expect(permsAfter.getByLabel("bash 命令白名单").getByText("rg *")).toBeVisible();
  });
});

async function loginAdmin(page: Page) {
  await page.goto("/#/login", { waitUntil: "networkidle" });
  await page.getByLabel("用户名").fill(ADMIN_USERNAME);
  await page.getByLabel("密码", { exact: true }).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByText("Admin")).toBeVisible();
}

async function openOpencodeConsole(page: Page) {
  await page.goto("/#/settings?page=runtime", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "OpenCode", exact: true })).toBeVisible();
}
