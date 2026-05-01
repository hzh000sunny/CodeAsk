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

    const globalSection = screen
      .getByRole("heading", { name: "全局 LLM 配置" })
      .closest("section");
    fireEvent.click(
      within(globalSection as HTMLElement).getByRole("button", {
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
});
