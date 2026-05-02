import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const adminMe = {
  subject_id: "admin",
  display_name: "Admin",
  role: "admin",
  authenticated: true,
};

const memberMe = {
  subject_id: "client_test",
  display_name: "client_test",
  role: "member",
  authenticated: false,
};

function llm(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "llm_2",
    name: "备用模型",
    scope: "global",
    owner_subject_id: null,
    protocol: "openai",
    base_url: "http://backup.internal/v1",
    api_key_masked: "sk-...bak",
    model_name: "qwen3",
    max_tokens: 2048,
    temperature: 0.4,
    is_default: false,
    enabled: true,
    rpm_limit: null,
    quota_remaining: null,
    ...overrides,
  };
}

const repo = {
  id: "repo_1",
  name: "platform-api",
  source: "local_dir",
  url: null,
  local_path: "/repo/platform-api",
  bare_path: "/tmp/repos/repo_1/bare",
  status: "ready",
  error_message: null,
  last_synced_at: null,
  created_at: "2026-04-30T10:00:00",
  updated_at: "2026-04-30T10:00:00",
};

const globalPolicy = {
  id: "sk_global_1",
  name: "证据引用规范",
  scope: "global",
  feature_id: null,
  stage: "answer_finalization",
  enabled: true,
  priority: 20,
  prompt_template: "回答必须引用证据 ID。",
};

describe("SettingsPage LLM configuration", () => {
  it("shows only login in the anonymous account menu and opens the admin login page", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") {
        return jsonResponse(memberMe);
      }
      if (path === "/api/sessions") {
        return jsonResponse([]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "未登录" }));
    expect(screen.getByRole("menuitem", { name: "登录" })).toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "退出" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "设置" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("menuitem", { name: "个人信息" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("menuitem", { name: "登录" }));
    expect(screen.getByRole("heading", { name: "登录" })).toBeInTheDocument();
    expect(screen.queryByText(/管理员/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("用户名")).toHaveValue("admin");
    const password = screen.getByLabelText("密码");
    expect(password).toHaveAttribute("type", "password");
    fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
    expect(password).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "隐藏密码" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("shows only user settings to ordinary members", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/auth/me") {
        return jsonResponse(memberMe);
      }
      if (path === "/api/sessions") {
        return jsonResponse([]);
      }
      if (path === "/api/me/llm-configs") {
        return jsonResponse([]);
      }
      throw new Error(`unexpected request ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(
      screen.queryByRole("heading", { name: "设置" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/权限隔离后普通用户/)).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "用户配置" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "全局配置" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "个人 LLM 配置" }),
    ).toBeInTheDocument();
  });

  it("creates a personal LLM config from user settings", async () => {
    let userConfigs: unknown[] = [];
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse(memberMe);
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs" && init?.method === "POST") {
          const created = llm({
            id: "llm_user_1",
            name: "个人模型",
            scope: "user",
            owner_subject_id: "client_test",
            model_name: "qwen3-coder",
            protocol: "anthropic",
          });
          userConfigs = [created];
          return jsonResponse(created, 201);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse(userConfigs);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    await screen.findByRole("heading", { name: "个人 LLM 配置" });

    fireEvent.click(screen.getByRole("button", { name: "添加 LLM 配置" }));
    fireEvent.change(screen.getByLabelText("配置名称"), {
      target: { value: "个人模型" },
    });
    const protocolSelect = screen.getByLabelText("消息接口协议");
    expect(protocolSelect).toHaveValue("openai");
    expect(
      within(protocolSelect).getByRole("option", { name: "OpenAI" }),
    ).toHaveValue("openai");
    expect(
      within(protocolSelect).getByRole("option", { name: "Anthropic" }),
    ).toHaveValue("anthropic");
    expect(screen.queryByLabelText("Max Tokens")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Temperature")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("RPM")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("剩余额度")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("设为默认配置")).not.toBeInTheDocument();
    fireEvent.change(protocolSelect, { target: { value: "anthropic" } });
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "http://llm.internal/v1" },
    });
    fireEvent.change(screen.getByLabelText("API Key"), {
      target: { value: "sk-test-abc" },
    });
    fireEvent.change(screen.getByLabelText("模型名称"), {
      target: { value: "qwen3-coder" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 LLM 配置" }));

    expect(await screen.findByText("个人模型")).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls.find(
      ([path, options]) =>
        path === "/api/me/llm-configs" &&
        (options as RequestInit | undefined)?.method === "POST",
    ) as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toMatchObject({
      name: "个人模型",
      protocol: "anthropic",
      base_url: "http://llm.internal/v1",
      api_key: "sk-test-abc",
      model_name: "qwen3-coder",
      enabled: true,
    });
    expect(JSON.parse(String(init.body))).not.toHaveProperty("max_tokens");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("temperature");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("is_default");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("rpm_limit");
    expect(JSON.parse(String(init.body))).not.toHaveProperty("quota_remaining");
  });

  it("shows a visible message when creating a LLM config fails", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse(memberMe);
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs" && init?.method === "POST") {
          return jsonResponse(
            { detail: "llm config name already exists" },
            409,
          );
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    await screen.findByRole("heading", { name: "个人 LLM 配置" });

    fireEvent.click(screen.getByRole("button", { name: "添加 LLM 配置" }));
    fireEvent.change(screen.getByLabelText("配置名称"), {
      target: { value: "重复模型" },
    });
    fireEvent.change(screen.getByLabelText("API Key"), {
      target: { value: "sk-test-abc" },
    });
    fireEvent.change(screen.getByLabelText("模型名称"), {
      target: { value: "qwen3-coder" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存 LLM 配置" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "保存 LLM 配置失败",
    );
    expect(
      screen.getByText(/llm config name already exists/),
    ).toBeInTheDocument();
  });

  it("edits, toggles, and deletes existing global LLM configs as admin without default controls", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse(adminMe);
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        if (path === "/api/repos") {
          return jsonResponse({ repos: [] });
        }
        if (path === "/api/skills") {
          return jsonResponse([]);
        }
        if (path === "/api/admin/llm-configs" && !init?.method) {
          return jsonResponse([llm()]);
        }
        if (
          path === "/api/admin/llm-configs/llm_2" &&
          init?.method === "PATCH"
        ) {
          const payload = JSON.parse(String(init.body));
          return jsonResponse(
            llm({
              ...payload,
              enabled: payload.enabled ?? false,
            }),
          );
        }
        if (
          path === "/api/admin/llm-configs/llm_2" &&
          init?.method === "DELETE"
        ) {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    expect(
      screen.queryByRole("heading", { name: "用户配置" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "个人 LLM 配置" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "全局配置" }),
    ).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "全局配置" }));
    expect(await screen.findByText("备用模型")).toBeInTheDocument();
    expect(screen.queryByText(/RPM/)).not.toBeInTheDocument();
    expect(screen.queryByText(/剩余额度/)).not.toBeInTheDocument();
    expect(screen.queryByText("默认")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "设为默认" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加 LLM 配置" })).toHaveClass(
      "button-primary",
    );
    const globalSection = screen
      .getByRole("heading", { name: "全局 LLM 配置" })
      .closest("section") as HTMLElement;
    fireEvent.click(
      within(globalSection).getByRole("button", { name: "添加 LLM 配置" }),
    );
    expect(
      within(globalSection).getByRole("button", { name: "取消" }),
    ).toBeInTheDocument();
    fireEvent.click(within(globalSection).getByRole("button", { name: "取消" }));
    expect(
      within(globalSection).queryByLabelText("配置名称"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("switch", { name: "备用模型 启用状态" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/llm-configs/llm_2",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ enabled: false }),
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "编辑 备用模型" }));
    fireEvent.change(screen.getByLabelText("编辑配置名称"), {
      target: { value: "主力模型" },
    });
    fireEvent.change(screen.getByLabelText("编辑消息接口协议"), {
      target: { value: "anthropic" },
    });
    fireEvent.change(screen.getByLabelText("编辑 Base URL"), {
      target: { value: "http://llm.new/v1" },
    });
    fireEvent.change(screen.getByLabelText("编辑 API Key"), {
      target: { value: "sk-new-key" },
    });
    fireEvent.change(screen.getByLabelText("编辑模型名称"), {
      target: { value: "claude-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));
    await waitFor(() => {
      const editCall = fetchMock.mock.calls.find(([path, options]) => {
        if (path !== "/api/admin/llm-configs/llm_2") {
          return false;
        }
        const body = JSON.parse(
          String((options as RequestInit | undefined)?.body),
        );
        return body.name === "主力模型";
      }) as unknown as [string, RequestInit] | undefined;
      expect(editCall).toBeDefined();
      expect(JSON.parse(String(editCall?.[1].body))).toMatchObject({
        name: "主力模型",
        protocol: "anthropic",
        base_url: "http://llm.new/v1",
        api_key: "sk-new-key",
        model_name: "claude-test",
      });
    });

    fireEvent.click(
      within(globalSection).getByRole("button", {
        name: "删除",
      }),
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/llm-configs/llm_2",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("edits repositories and manages global analysis policies as admin", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (path === "/api/auth/me") {
          return jsonResponse(adminMe);
        }
        if (path === "/api/sessions") {
          return jsonResponse([]);
        }
        if (path === "/api/me/llm-configs") {
          return jsonResponse([]);
        }
        if (path === "/api/admin/llm-configs") {
          return jsonResponse([]);
        }
        if (path === "/api/repos" && !init?.method) {
          return jsonResponse({ repos: [repo] });
        }
        if (path === "/api/repos/repo_1" && init?.method === "PATCH") {
          return jsonResponse({
            ...repo,
            ...JSON.parse(String(init.body)),
            name: "platform-api-renamed",
            local_path: "/repo/platform-api-next",
          });
        }
        if (path === "/api/repos/repo_1/refresh" && init?.method === "POST") {
          return jsonResponse({ ...repo, status: "cloning" });
        }
        if (path === "/api/skills" && !init?.method) {
          return jsonResponse([globalPolicy]);
        }
        if (path === "/api/skills" && init?.method === "POST") {
          return jsonResponse(
            {
              id: "sk_global_2",
              scope: "global",
              feature_id: null,
              enabled: true,
              ...JSON.parse(String(init.body)),
            },
            201,
          );
        }
        if (path === "/api/skills/sk_global_1" && init?.method === "PATCH") {
          return jsonResponse({
            ...globalPolicy,
            ...JSON.parse(String(init.body)),
          });
        }
        if (path === "/api/skills/sk_global_1" && init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        throw new Error(`unexpected request ${path}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(
      await screen.findByRole("heading", { name: "仓库管理" }),
    ).toBeInTheDocument();
    const repoSection = screen
      .getByRole("heading", { name: "仓库管理" })
      .closest("section") as HTMLElement;
    expect(
      within(repoSection).getByText(
        "维护 CodeAsk 后端用于代码检索和 Agent 调查的全局仓库缓存。",
      ),
    ).toBeInTheDocument();
    expect(
      within(repoSection).getByRole("button", { name: "添加仓库" }),
    ).toHaveClass("button-primary");
    expect(
      within(repoSection).queryByLabelText("仓库名称"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      within(repoSection).getByRole("button", { name: "添加仓库" }),
    );
    const createRepoForm = within(repoSection)
      .getByLabelText("仓库名称")
      .closest("form") as HTMLElement;
    expect(createRepoForm).toHaveClass("repo-edit-form", "repo-create-form");
    expect(
      Array.from(createRepoForm.querySelectorAll("label")).map((label) =>
        label.childNodes[0]?.textContent?.trim(),
      ),
    ).toEqual(["仓库名称", "类型", "本地路径"]);
    const settingsContent = screen
      .getByRole("heading", { name: "仓库管理" })
      .closest(".settings-content");
    expect(settingsContent).not.toBeNull();
    expect(settingsContent).toHaveAttribute("data-scroll-region", "true");
    expect(await screen.findByText("platform-api")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "刷新" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "编辑仓库 platform-api" }),
    );
    expect(screen.getByLabelText("编辑仓库名称").closest("label")).toHaveClass(
      "repo-edit-field",
    );
    expect(screen.getByLabelText("编辑仓库类型").closest("label")).toHaveClass(
      "repo-edit-field",
    );
    expect(screen.getByLabelText("编辑本地路径").closest("label")).toHaveClass(
      "repo-edit-field",
      "repo-location-field",
    );
    fireEvent.change(screen.getByLabelText("编辑仓库名称"), {
      target: { value: "platform-api-renamed" },
    });
    fireEvent.change(screen.getByLabelText("编辑本地路径"), {
      target: { value: "/repo/platform-api-next" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存仓库" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/repos/repo_1",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            name: "platform-api-renamed",
            source: "local_dir",
            local_path: "/repo/platform-api-next",
            url: null,
          }),
        }),
      );
    });
    fireEvent.click(
      screen.getByRole("button", { name: "同步仓库 platform-api" }),
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/repos/repo_1/refresh",
        expect.objectContaining({ method: "POST" }),
      );
    });

    expect(
      await screen.findByRole("heading", { name: "全局分析策略" }),
    ).toBeInTheDocument();
    expect(screen.getByText("证据引用规范")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "添加分析策略" }));
    const createPolicyForm = screen
      .getByLabelText("策略名称")
      .closest("form") as HTMLElement;
    expect(createPolicyForm).toHaveClass("policy-form");
    fireEvent.change(screen.getByLabelText("策略名称"), {
      target: { value: "代码调查规范" },
    });
    fireEvent.change(screen.getByLabelText("适用阶段"), {
      target: { value: "code_investigation" },
    });
    fireEvent.change(screen.getByLabelText("优先级"), {
      target: { value: "5" },
    });
    fireEvent.change(screen.getByLabelText("Prompt 内容"), {
      target: { value: "代码调查必须先定位入口函数。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建分析策略" }));
    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([path, options]) =>
          path === "/api/skills" &&
          (options as RequestInit | undefined)?.method === "POST",
      ) as unknown as [string, RequestInit] | undefined;
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1].body))).toMatchObject({
        name: "代码调查规范",
        scope: "global",
        feature_id: null,
        stage: "code_investigation",
        priority: 5,
        enabled: true,
        prompt_template: "代码调查必须先定位入口函数。",
      });
    });

    fireEvent.click(
      screen.getByRole("button", { name: "编辑分析策略 证据引用规范" }),
    );
    const editPolicyForm = screen
      .getByLabelText("策略名称")
      .closest("form") as HTMLElement;
    expect(editPolicyForm).toHaveClass("policy-form");
    expect(editPolicyForm.closest("li")).toHaveAttribute(
      "data-editing",
      "true",
    );
    fireEvent.click(within(editPolicyForm).getByRole("button", { name: "取消" }));

    fireEvent.click(
      screen.getByRole("switch", { name: "证据引用规范 启用状态" }),
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/skills/sk_global_1",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ enabled: false }),
        }),
      );
    });
  });
});
