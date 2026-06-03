import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppFeedbackProvider } from "../src/components/feedback/AppFeedback";
import { OpencodeToolPermissionsPanel } from "../src/components/settings/OpencodeToolPermissionsPanel";
import * as api from "../src/lib/api-opencode";

vi.mock("../src/lib/api-opencode", async () => {
  const actual = await vi.importActual<typeof import("../src/lib/api-opencode")>(
    "../src/lib/api-opencode",
  );
  return {
    ...actual,
    getOpencodePermissions: vi.fn(),
    updateOpencodePermissions: vi.fn(),
  };
});

function permissionsResponse(overrides: Partial<api.OpencodePermissionsResponse> = {}) {
  return {
    tools: {
      read: "allow",
      grep: "allow",
      glob: "allow",
      webfetch: "deny",
      edit: "deny",
      write: "deny",
      openviking_remember: "deny",
      openviking_add_resource: "deny",
      openviking_forget: "deny",
    },
    bash: { mode: "deny", patterns: [] },
    openviking_enabled: false,
    catalog: {
      tools: [
        { key: "read", label: "读取文件", purpose: "读取工作区内容", group: "read", openviking: false },
        { key: "grep", label: "内容检索", purpose: "搜索", group: "search", openviking: false },
        { key: "edit", label: "编辑文件", purpose: "修改", group: "write", openviking: false },
      ],
      bash_suggestions: ["git status", "ls *"],
    },
    defaults: {
      version: 1,
      tools: {
        read: "allow",
        grep: "allow",
        glob: "allow",
        webfetch: "deny",
        edit: "deny",
        write: "deny",
        openviking_remember: "deny",
        openviking_add_resource: "deny",
        openviking_forget: "deny",
      },
      bash: { mode: "deny", patterns: [] },
    },
    ...overrides,
  } as api.OpencodePermissionsResponse;
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AppFeedbackProvider>
        <OpencodeToolPermissionsPanel />
      </AppFeedbackProvider>
    </QueryClientProvider>,
  );
}

describe("OpencodeToolPermissionsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOpencodePermissions).mockResolvedValue(permissionsResponse());
    vi.mocked(api.updateOpencodePermissions).mockImplementation((payload) =>
      Promise.resolve(permissionsResponse({ tools: { ...permissionsResponse().tools, ...payload.tools }, bash: payload.bash })),
    );
  });

  it("renders the tool matrix and keeps save disabled until something changes", async () => {
    renderPanel();

    expect(await screen.findByText("读取文件")).toBeInTheDocument();
    expect(screen.getByText("编辑文件")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
  });

  it("does not render OpenViking write tools when OpenViking is disabled", async () => {
    renderPanel();
    await screen.findByText("读取文件");
    expect(screen.queryByText("OpenViking 记忆")).not.toBeInTheDocument();
  });

  it("saves a toggled tool through the confirm dialog", async () => {
    renderPanel();
    await screen.findByText("编辑文件");

    const editRow = screen.getByText("编辑文件").closest(".opencode-tool-row") as HTMLElement;
    fireEvent.click(within(editRow).getByRole("radio", { name: "允许" }));

    const save = screen.getByRole("button", { name: "保存" });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    // Confirm dialog appears; confirming triggers the update.
    fireEvent.click(await screen.findByRole("button", { name: "确认保存" }));

    await waitFor(() => expect(api.updateOpencodePermissions).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(api.updateOpencodePermissions).mock.calls[0][0];
    expect(payload.tools.edit).toBe("allow");
    expect(await screen.findByText("工具权限已保存，对新建会话生效")).toBeInTheDocument();
  });

  it("reveals the terminal allowlist in whitelist mode and adds patterns", async () => {
    renderPanel();
    await screen.findByText("Shell 命令");

    const bashRow = screen.getByText("Shell 命令").closest(".opencode-bash-row") as HTMLElement;
    fireEvent.click(within(bashRow).getByRole("radio", { name: "白名单" }));

    expect(await screen.findByLabelText("bash 命令白名单")).toBeInTheDocument();

    // Quick-fill recommended commands.
    fireEvent.click(screen.getByRole("button", { name: /填入推荐/ }));
    expect(screen.getByText("git status")).toBeInTheDocument();
    expect(screen.getByText("ls *")).toBeInTheDocument();

    // Add a custom pattern via the input.
    const input = screen.getByLabelText("添加命令通配符");
    fireEvent.change(input, { target: { value: "rg *" } });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    expect(screen.getByText("rg *")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认保存" }));

    await waitFor(() => expect(api.updateOpencodePermissions).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(api.updateOpencodePermissions).mock.calls[0][0];
    expect(payload.bash.mode).toBe("whitelist");
    expect(payload.bash.patterns).toEqual(["git status", "ls *", "rg *"]);
  });

  it("shows an error toast when saving fails", async () => {
    vi.mocked(api.updateOpencodePermissions).mockRejectedValue(new Error("boom"));
    renderPanel();
    await screen.findByText("编辑文件");

    const editRow = screen.getByText("编辑文件").closest(".opencode-tool-row") as HTMLElement;
    fireEvent.click(within(editRow).getByRole("radio", { name: "允许" }));
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认保存" }));

    expect(await screen.findByText(/保存工具权限失败/)).toBeInTheDocument();
  });
});
