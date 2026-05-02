import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  GitBranch,
  KeyRound,
  Pencil,
  Plus,
  RefreshCw,
  Settings2,
  Trash2,
  UserRound,
} from "lucide-react";

import {
  createAdminLlmConfig,
  createRepo,
  createUserLlmConfig,
  deleteAdminLlmConfig,
  deleteRepo,
  deleteUserLlmConfig,
  getMe,
  listAdminLlmConfigs,
  listRepos,
  listUserLlmConfigs,
  refreshRepo,
  updateAdminLlmConfig,
  updateRepo,
  updateUserLlmConfig,
} from "../../lib/api";
import { getNickname, getSubjectId, setNickname } from "../../lib/identity";
import type { LLMConfigResponse, RepoOut } from "../../types/api";
import { AnalysisPolicyManager } from "../policies/AnalysisPolicyManager";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

type LlmScope = "user" | "global";
type LlmProtocol = "openai" | "anthropic";
type LlmUpdatePayload = Partial<{
  name: string;
  protocol: LlmProtocol;
  base_url: string | null;
  api_key: string;
  model_name: string;
  enabled: boolean;
}>;

export function SettingsPage() {
  const [indexCollapsed, setIndexCollapsed] = useState(false);
  const { data: me } = useQuery({ queryKey: ["auth", "me"], queryFn: getMe });
  const isAdmin = me?.role === "admin";

  return (
    <section
      className="settings-workspace"
      data-index-collapsed={indexCollapsed}
      aria-label="设置工作台"
    >
      <aside className="settings-index" data-collapsed={indexCollapsed}>
        <button
          aria-label={indexCollapsed ? "展开设置导航" : "收起设置导航"}
          className="edge-collapse-button secondary"
          data-collapsed={indexCollapsed}
          onClick={() => setIndexCollapsed((value) => !value)}
          title={indexCollapsed ? "展开设置导航" : "收起设置导航"}
          type="button"
        >
          {indexCollapsed ? (
            <ChevronRight aria-hidden="true" size={15} />
          ) : (
            <ChevronLeft aria-hidden="true" size={15} />
          )}
        </button>
        {indexCollapsed ? (
          <div className="collapsed-panel-label">设置</div>
        ) : (
          <>
            {!me ? <p className="empty-note">正在加载设置</p> : null}
            {me && !isAdmin ? (
              <button
                aria-current="page"
                className="settings-index-item"
                data-active="true"
                type="button"
              >
                <UserRound aria-hidden="true" size={17} />
                <span>用户设置</span>
              </button>
            ) : null}
            {isAdmin ? (
              <button
                aria-current="page"
                className="settings-index-item"
                data-active="true"
                type="button"
              >
                <Settings2 aria-hidden="true" size={17} />
                <span>全局配置</span>
              </button>
            ) : null}
          </>
        )}
      </aside>

      <section className="settings-content" data-scroll-region="true">
        {!me ? <SettingsLoading /> : null}
        {me && !isAdmin ? <UserSettings /> : null}
        {isAdmin ? <GlobalSettings /> : null}
      </section>
    </section>
  );
}

function SettingsLoading() {
  return (
    <div className="settings-stack">
      <section className="surface">
        <p className="empty-note">正在加载设置</p>
      </section>
    </div>
  );
}

function UserSettings() {
  const [nickname, setNicknameValue] = useState(getNickname());
  const [saved, setSaved] = useState(false);

  return (
    <div className="settings-stack">
      <section className="surface">
        <div className="section-title">
          <UserRound aria-hidden="true" size={18} />
          <h2>用户配置</h2>
        </div>
        <dl className="meta-grid">
          <dt>Subject ID</dt>
          <dd>{getSubjectId()}</dd>
        </dl>
        <label className="field-label">
          昵称
          <Input
            onChange={(event) => {
              setSaved(false);
              setNicknameValue(event.target.value);
            }}
            placeholder="可选"
            value={nickname}
          />
        </label>
        <div className="form-actions">
          <Button
            onClick={() => {
              setNickname(nickname);
              setSaved(true);
            }}
            type="button"
            variant="primary"
          >
            保存用户设置
          </Button>
          {saved ? <span className="action-status inline">已保存</span> : null}
        </div>
      </section>
      <LlmConfigManager scope="user" />
    </div>
  );
}

function GlobalSettings() {
  return (
    <div className="settings-stack">
      <LlmConfigManager scope="global" />
      <RepoManager />
      <AnalysisPolicyManager
        description="全局策略会注入 Agent 上下文，约束问题定位、代码调查和最终回答。"
        scope="global"
        title="全局分析策略"
      />
    </div>
  );
}

function LlmConfigManager({ scope }: { scope: LlmScope }) {
  const queryClient = useQueryClient();
  const noticeTimeoutRef = useRef<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [configName, setConfigName] = useState("");
  const [protocol, setProtocol] = useState<LlmProtocol>("openai");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [notice, setNotice] = useState<{
    tone: "success" | "danger";
    message: string;
  } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const queryKey =
    scope === "global" ? ["admin-llm-configs"] : ["user-llm-configs"];
  const { data: configs = [] } = useQuery({
    queryKey,
    queryFn: scope === "global" ? listAdminLlmConfigs : listUserLlmConfigs,
  });

  useEffect(() => {
    return () => {
      if (noticeTimeoutRef.current) {
        window.clearTimeout(noticeTimeoutRef.current);
      }
    };
  }, []);

  const createMutation = useMutation({
    mutationFn: () => {
      const payload = {
        name: configName.trim(),
        protocol,
        base_url: baseUrl.trim() || null,
        api_key: apiKey,
        model_name: modelName.trim(),
        enabled,
      };
      return scope === "global"
        ? createAdminLlmConfig(payload)
        : createUserLlmConfig(payload);
    },
    onSuccess: () => {
      showNotice("success", "LLM 配置已保存");
      setShowForm(false);
      resetCreateForm();
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `保存 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: LlmUpdatePayload }) =>
      scope === "global"
        ? updateAdminLlmConfig(id, payload)
        : updateUserLlmConfig(id, payload),
    onSuccess: () => {
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `更新 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      scope === "global" ? deleteAdminLlmConfig(id) : deleteUserLlmConfig(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      showNotice("danger", `删除 LLM 配置失败：${messageFromApiError(error)}`);
    },
  });

  function showNotice(tone: "success" | "danger", message: string) {
    if (noticeTimeoutRef.current) {
      window.clearTimeout(noticeTimeoutRef.current);
    }
    setNotice({ tone, message });
    noticeTimeoutRef.current = window.setTimeout(() => {
      setNotice(null);
      noticeTimeoutRef.current = null;
    }, 3200);
  }

  function resetCreateForm() {
    setConfigName("");
    setProtocol("openai");
    setBaseUrl("");
    setApiKey("");
    setModelName("");
    setEnabled(true);
  }

  return (
    <section className="surface">
      <div className="section-title">
        <KeyRound aria-hidden="true" size={18} />
        <h2>{scope === "global" ? "全局 LLM 配置" : "个人 LLM 配置"}</h2>
      </div>
      <div className="content-toolbar slim">
        <p>
          {scope === "global"
            ? "管理员可维护多个全局账号，启用状态决定是否参与运行时选择。"
            : "个人配置优先于全局配置，用于覆盖自己的模型账号。"}
        </p>
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowForm((value) => !value)}
          type="button"
          variant="primary"
        >
          添加 LLM 配置
        </Button>
      </div>
      {notice ? (
        <div
          className="settings-toast"
          data-tone={notice.tone}
          role={notice.tone === "danger" ? "alert" : "status"}
        >
          {notice.message}
        </div>
      ) : null}
      {showForm ? (
        <form
          className="inline-form llm-form llm-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate();
          }}
        >
          <label className="field-label compact">
            配置名称
            <Input
              onChange={(event) => setConfigName(event.target.value)}
              value={configName}
            />
          </label>
          <label className="field-label compact">
            消息接口协议
            <select
              className="input"
              onChange={(event) =>
                setProtocol(event.target.value as LlmProtocol)
              }
              value={protocol}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>
          <label className="field-label compact">
            Base URL
            <Input
              onChange={(event) => setBaseUrl(event.target.value)}
              value={baseUrl}
            />
          </label>
          <label className="field-label compact">
            API Key
            <Input
              onChange={(event) => setApiKey(event.target.value)}
              type="password"
              value={apiKey}
            />
          </label>
          <label className="field-label compact">
            模型名称
            <Input
              onChange={(event) => setModelName(event.target.value)}
              value={modelName}
            />
          </label>
          <div className="form-switches">
            <SwitchControl
              checked={enabled}
              label="新配置启用状态"
              onChange={setEnabled}
              text={enabled ? "启用" : "停用"}
            />
          </div>
          <div className="form-actions">
            <Button
              disabled={
                !configName.trim() ||
                !apiKey ||
                !modelName.trim() ||
                createMutation.isPending
              }
              type="submit"
              variant="primary"
            >
              保存 LLM 配置
            </Button>
            <Button
              disabled={createMutation.isPending}
              onClick={() => {
                setShowForm(false);
                resetCreateForm();
              }}
              type="button"
              variant="quiet"
            >
              取消
            </Button>
          </div>
        </form>
      ) : null}
      <LlmConfigList
        configs={configs}
        deleting={deleteMutation.isPending}
        editingId={editingId}
        onDelete={(id) => deleteMutation.mutate(id)}
        onEditCancel={() => setEditingId(null)}
        onEditStart={(id) => setEditingId(id)}
        onUpdate={(id, payload) => updateMutation.mutate({ id, payload })}
        onToggleEnabled={(config) =>
          updateMutation.mutate({
            id: config.id,
            payload: { enabled: !config.enabled },
          })
        }
        updating={updateMutation.isPending}
      />
    </section>
  );
}

function LlmConfigList({
  configs,
  deleting,
  editingId,
  onDelete,
  onEditCancel,
  onEditStart,
  onUpdate,
  onToggleEnabled,
  updating,
}: {
  configs: LLMConfigResponse[];
  deleting: boolean;
  editingId: string | null;
  onDelete: (id: string) => void;
  onEditCancel: () => void;
  onEditStart: (id: string) => void;
  onUpdate: (id: string, payload: LlmUpdatePayload) => void;
  onToggleEnabled: (config: LLMConfigResponse) => void;
  updating: boolean;
}) {
  if (configs.length === 0) {
    return (
      <div className="empty-block wide">
        <p>暂无 LLM 配置</p>
      </div>
    );
  }
  return (
    <ul className="data-list settings-config-list">
      {configs.map((config) => {
        const isEditing = editingId === config.id;
        return (
          <li data-editing={isEditing} key={config.id}>
            <div className="config-row-main">
              <div className="config-summary">
                <span>{config.name}</span>
                <small>
                  {protocolLabel(config.protocol)} · {config.model_name} ·{" "}
                  {config.api_key_masked}
                </small>
              </div>
              <div className="row-actions">
                <SwitchControl
                  checked={config.enabled}
                  disabled={updating}
                  label={`${config.name} 启用状态`}
                  onChange={() => onToggleEnabled(config)}
                  text={config.enabled ? "启用" : "停用"}
                />
                <Button
                  aria-label={`编辑 ${config.name}`}
                  disabled={updating}
                  icon={<Pencil size={15} />}
                  onClick={() => onEditStart(config.id)}
                  type="button"
                  variant="quiet"
                >
                  编辑
                </Button>
                <Button
                  disabled={deleting}
                  icon={<Trash2 size={15} />}
                  onClick={() => onDelete(config.id)}
                  type="button"
                  variant="quiet"
                >
                  删除
                </Button>
              </div>
            </div>
            {isEditing ? (
              <LlmConfigEditForm
                config={config}
                disabled={updating}
                onCancel={onEditCancel}
                onSubmit={(payload) => onUpdate(config.id, payload)}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function LlmConfigEditForm({
  config,
  disabled,
  onCancel,
  onSubmit,
}: {
  config: LLMConfigResponse;
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (payload: LlmUpdatePayload) => void;
}) {
  const [name, setName] = useState(config.name);
  const [protocol, setProtocol] = useState<LlmProtocol>(
    safeEditableProtocol(config.protocol),
  );
  const [baseUrl, setBaseUrl] = useState(config.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [modelName, setModelName] = useState(config.model_name);

  return (
    <form
      className="inline-form llm-form llm-edit-form"
      onSubmit={(event) => {
        event.preventDefault();
        const payload: LlmUpdatePayload = {
          name: name.trim(),
          protocol,
          base_url: baseUrl.trim() || null,
          model_name: modelName.trim(),
        };
        if (apiKey) {
          payload.api_key = apiKey;
        }
        onSubmit(payload);
      }}
    >
      <label className="field-label compact">
        编辑配置名称
        <Input onChange={(event) => setName(event.target.value)} value={name} />
      </label>
      <label className="field-label compact">
        编辑消息接口协议
        <select
          className="input"
          onChange={(event) => setProtocol(event.target.value as LlmProtocol)}
          value={protocol}
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </label>
      <label className="field-label compact">
        编辑 Base URL
        <Input
          onChange={(event) => setBaseUrl(event.target.value)}
          value={baseUrl}
        />
      </label>
      <label className="field-label compact">
        编辑 API Key
        <Input
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="留空则不修改"
          type="password"
          value={apiKey}
        />
      </label>
      <label className="field-label compact">
        编辑模型名称
        <Input
          onChange={(event) => setModelName(event.target.value)}
          value={modelName}
        />
      </label>
      <div className="form-actions llm-edit-actions">
        <Button
          disabled={!name.trim() || !modelName.trim() || disabled}
          type="submit"
          variant="primary"
        >
          保存修改
        </Button>
        <Button
          disabled={disabled}
          onClick={onCancel}
          type="button"
          variant="quiet"
        >
          取消
        </Button>
      </div>
    </form>
  );
}

function SwitchControl({
  checked,
  disabled,
  label,
  onChange,
  text,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  text: string;
}) {
  return (
    <label
      className="switch-control"
      data-checked={checked}
      data-disabled={disabled ? "true" : "false"}
    >
      <input
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        role="switch"
        type="checkbox"
      />
      <span aria-hidden="true" className="switch-track" />
      <span className="switch-text">{text}</span>
    </label>
  );
}

function safeEditableProtocol(protocol: string): LlmProtocol {
  return protocol === "anthropic" ? "anthropic" : "openai";
}

function protocolLabel(protocol: string) {
  if (protocol === "anthropic") {
    return "Anthropic";
  }
  if (protocol === "openai_compatible") {
    return "OpenAI Compatible";
  }
  return "OpenAI";
}

function messageFromApiError(error: unknown) {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (typeof detail === "object" && detail !== null && "detail" in detail) {
      const nested = (detail as { detail?: unknown }).detail;
      if (typeof nested === "string") {
        return nested;
      }
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败";
}

function RepoManager() {
  const queryClient = useQueryClient();
  const noticeTimeoutRef = useRef<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [source, setSource] = useState<"local_dir" | "git">("local_dir");
  const [location, setLocation] = useState("");
  const [notice, setNotice] = useState<{
    tone: "success" | "danger";
    message: string;
  } | null>(null);
  const { data: repos = [] } = useQuery({
    queryKey: ["repos"],
    queryFn: listRepos,
  });

  useEffect(() => {
    return () => {
      if (noticeTimeoutRef.current) {
        window.clearTimeout(noticeTimeoutRef.current);
      }
    };
  }, []);

  function showNotice(tone: "success" | "danger", message: string) {
    if (noticeTimeoutRef.current) {
      window.clearTimeout(noticeTimeoutRef.current);
    }
    setNotice({ tone, message });
    noticeTimeoutRef.current = window.setTimeout(() => {
      setNotice(null);
      noticeTimeoutRef.current = null;
    }, 3200);
  }

  const createMutation = useMutation({
    mutationFn: () =>
      createRepo({
        name: name.trim(),
        source,
        local_path: source === "local_dir" ? location.trim() : null,
        url: source === "git" ? location.trim() : null,
      }),
    onSuccess: () => {
      setName("");
      setSource("local_dir");
      setLocation("");
      setShowForm(false);
      showNotice("success", "仓库已添加");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `添加仓库失败：${messageFromApiError(error)}`);
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({
      repoId,
      payload,
    }: {
      repoId: string;
      payload: {
        name: string;
        source: "git" | "local_dir";
        url: string | null;
        local_path: string | null;
      };
    }) => updateRepo(repoId, payload),
    onSuccess: () => {
      showNotice("success", "仓库已保存");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `保存仓库失败：${messageFromApiError(error)}`);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteRepo,
    onSuccess: () => {
      showNotice("success", "仓库已删除");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `删除仓库失败：${messageFromApiError(error)}`);
    },
  });
  const refreshMutation = useMutation({
    mutationFn: refreshRepo,
    onSuccess: () => {
      showNotice("success", "仓库同步已提交");
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (error) => {
      showNotice("danger", `同步仓库失败：${messageFromApiError(error)}`);
    },
  });

  return (
    <section className="surface">
      <div className="section-title">
        <GitBranch aria-hidden="true" size={18} />
        <h2>仓库管理</h2>
      </div>
      <div className="content-toolbar slim">
        <p>维护 CodeAsk 后端用于代码检索和 Agent 调查的全局仓库缓存。</p>
        <Button
          icon={<Plus size={15} />}
          onClick={() => setShowForm((value) => !value)}
          type="button"
          variant="primary"
        >
          添加仓库
        </Button>
      </div>
      {notice ? (
        <div
          className="settings-toast"
          data-tone={notice.tone}
          role={notice.tone === "danger" ? "alert" : "status"}
        >
          {notice.message}
        </div>
      ) : null}
      {showForm ? (
        <form
          className="inline-form repo-edit-form repo-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            createMutation.mutate();
          }}
        >
          <label className="field-label compact repo-edit-field">
            仓库名称
            <Input
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label className="field-label compact repo-edit-field">
            类型
            <select
              className="input"
              onChange={(event) =>
                setSource(event.target.value as "local_dir" | "git")
              }
              value={source}
            >
              <option value="local_dir">本地目录</option>
              <option value="git">Git URL</option>
            </select>
          </label>
          <label className="field-label compact repo-edit-field repo-location-field">
            {source === "local_dir" ? "本地路径" : "Git URL"}
            <Input
              onChange={(event) => setLocation(event.target.value)}
              value={location}
            />
          </label>
          <div className="form-actions">
            <Button
              disabled={
                !name.trim() || !location.trim() || createMutation.isPending
              }
              type="submit"
              variant="primary"
            >
              创建仓库
            </Button>
            <Button
              disabled={createMutation.isPending}
              onClick={() => {
                setShowForm(false);
                setName("");
                setSource("local_dir");
                setLocation("");
              }}
              type="button"
              variant="quiet"
            >
              取消
            </Button>
          </div>
        </form>
      ) : null}
      {repos.length === 0 ? (
        <div className="empty-block wide">
          <p>暂无仓库</p>
        </div>
      ) : (
        <ul className="data-list settings-config-list">
          {repos.map((repo) => (
            <RepoRow
              key={repo.id}
              deleting={deleteMutation.isPending}
              onDelete={() => deleteMutation.mutate(repo.id)}
              onRefresh={() => refreshMutation.mutate(repo.id)}
              onUpdate={(payload) =>
                updateMutation.mutate({ repoId: repo.id, payload })
              }
              refreshing={refreshMutation.isPending}
              repo={repo}
              updating={updateMutation.isPending}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function RepoRow({
  deleting,
  onDelete,
  onRefresh,
  onUpdate,
  refreshing,
  repo,
  updating,
}: {
  deleting: boolean;
  onDelete: () => void;
  onRefresh: () => void;
  onUpdate: (payload: {
    name: string;
    source: "git" | "local_dir";
    url: string | null;
    local_path: string | null;
  }) => void;
  refreshing: boolean;
  repo: RepoOut;
  updating: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(repo.name);
  const [source, setSource] = useState<"git" | "local_dir">(repo.source);
  const [location, setLocation] = useState(
    repo.source === "git" ? (repo.url ?? "") : (repo.local_path ?? ""),
  );
  const syncLabel = repo.status === "failed" ? "重试同步" : "同步";
  const locationLabel =
    source === "local_dir" ? "编辑本地路径" : "编辑 Git URL";

  return (
    <li data-editing={editing ? "true" : undefined}>
      {editing ? (
        <form
          className="inline-form repo-edit-form"
          onSubmit={(event) => {
            event.preventDefault();
            onUpdate({
              name: name.trim(),
              source,
              local_path: source === "local_dir" ? location.trim() : null,
              url: source === "git" ? location.trim() : null,
            });
            setEditing(false);
          }}
        >
          <label className="field-label compact repo-edit-field">
            编辑仓库名称
            <Input
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <label className="field-label compact repo-edit-field">
            编辑仓库类型
            <select
              className="input"
              onChange={(event) =>
                setSource(event.target.value as "git" | "local_dir")
              }
              value={source}
            >
              <option value="local_dir">本地目录</option>
              <option value="git">Git URL</option>
            </select>
          </label>
          <label className="field-label compact repo-edit-field repo-location-field">
            {locationLabel}
            <Input
              onChange={(event) => setLocation(event.target.value)}
              value={location}
            />
          </label>
          <div className="form-actions">
            <Button
              disabled={!name.trim() || !location.trim() || updating}
              type="submit"
              variant="primary"
            >
              保存仓库
            </Button>
            <Button
              disabled={updating}
              onClick={() => setEditing(false)}
              type="button"
              variant="quiet"
            >
              取消
            </Button>
          </div>
        </form>
      ) : (
        <>
          <div className="config-summary">
            <span>{repo.name}</span>
            <small>{repo.source === "git" ? repo.url : repo.local_path}</small>
          </div>
          <div className="row-actions">
            <Badge>{repo.status}</Badge>
            <Button
              aria-label={`编辑仓库 ${repo.name}`}
              disabled={updating}
              icon={<Pencil size={15} />}
              onClick={() => setEditing(true)}
              type="button"
              variant="quiet"
            >
              编辑
            </Button>
            <Button
              aria-label={`${syncLabel}仓库 ${repo.name}`}
              disabled={refreshing}
              icon={<RefreshCw size={15} />}
              onClick={onRefresh}
              type="button"
              variant="quiet"
            >
              {syncLabel}
            </Button>
            <Button
              disabled={deleting}
              icon={<Trash2 size={15} />}
              onClick={onDelete}
              type="button"
              variant="quiet"
            >
              删除
            </Button>
          </div>
        </>
      )}
    </li>
  );
}
