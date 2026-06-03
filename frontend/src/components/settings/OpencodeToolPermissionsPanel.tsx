import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Brain,
  Database,
  FilePlus2,
  FileText,
  FolderSearch,
  Globe,
  PenLine,
  Plus,
  RotateCcw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Trash2,
  X,
} from "lucide-react";

import {
  getOpencodePermissions,
  updateOpencodePermissions,
  type OpencodeBashMode,
  type OpencodePermissionsResponse,
  type OpencodePermissionValue,
  type OpencodeToolCatalogItem,
} from "../../lib/api-opencode";
import { useAppFeedback } from "../feedback/AppFeedback";
import { messageFromApiError } from "./settings-utils";

const TOOL_ICONS: Record<string, typeof FileText> = {
  read: FileText,
  grep: Search,
  glob: FolderSearch,
  webfetch: Globe,
  edit: PenLine,
  write: FilePlus2,
  openviking_remember: Brain,
  openviking_add_resource: Database,
  openviking_forget: Trash2,
};

const GROUP_LABELS: Record<string, string> = {
  read: "读取",
  search: "检索",
  network: "网络",
  write: "写入",
  openviking: "OpenViking 写入",
  other: "其它",
};

const GROUP_ORDER = ["read", "search", "network", "write", "openviking", "other"];

interface FormState {
  tools: Record<string, OpencodePermissionValue>;
  bashMode: OpencodeBashMode;
  bashPatterns: string[];
}

function formFromResponse(data: OpencodePermissionsResponse): FormState {
  return {
    tools: { ...data.tools },
    bashMode: data.bash.mode,
    bashPatterns: [...data.bash.patterns],
  };
}

function serialize(form: FormState): string {
  const tools = Object.keys(form.tools)
    .sort()
    .map((key) => `${key}=${form.tools[key]}`)
    .join(",");
  return `${tools}|${form.bashMode}|${[...form.bashPatterns].join("\n")}`;
}

export function OpencodeToolPermissionsPanel() {
  const feedback = useAppFeedback();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);
  const [baseline, setBaseline] = useState<string>("");

  const permsQuery = useQuery({
    queryKey: ["admin-opencode-permissions"],
    queryFn: getOpencodePermissions,
  });

  const data = permsQuery.data;

  useEffect(() => {
    if (data) {
      const next = formFromResponse(data);
      setForm(next);
      setBaseline(serialize(next));
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: updateOpencodePermissions,
    onSuccess: (response) => {
      const next = formFromResponse(response);
      setForm(next);
      setBaseline(serialize(next));
      feedback.showSuccess("工具权限已保存，对新建会话生效");
    },
    onError: (error) =>
      feedback.showError(`保存工具权限失败：${messageFromApiError(error)}`),
  });

  const dirty = useMemo(() => (form ? serialize(form) !== baseline : false), [form, baseline]);

  const grouped = useMemo(() => {
    if (!data) {
      return [] as Array<{ group: string; items: OpencodeToolCatalogItem[] }>;
    }
    const buckets = new Map<string, OpencodeToolCatalogItem[]>();
    for (const item of data.catalog.tools) {
      const list = buckets.get(item.group) ?? [];
      list.push(item);
      buckets.set(item.group, list);
    }
    return GROUP_ORDER.filter((group) => buckets.has(group)).map((group) => ({
      group,
      items: buckets.get(group) ?? [],
    }));
  }, [data]);

  function setToolValue(key: string, value: OpencodePermissionValue) {
    setForm((current) =>
      current ? { ...current, tools: { ...current.tools, [key]: value } } : current,
    );
  }

  function setBashMode(mode: OpencodeBashMode) {
    setForm((current) => (current ? { ...current, bashMode: mode } : current));
  }

  function setBashPatterns(patterns: string[]) {
    setForm((current) => (current ? { ...current, bashPatterns: patterns } : current));
  }

  function resetToDefaults() {
    if (!data) {
      return;
    }
    setForm({
      tools: { ...data.defaults.tools },
      bashMode: data.defaults.bash.mode,
      bashPatterns: [...data.defaults.bash.patterns],
    });
  }

  function handleSave() {
    if (!form) {
      return;
    }
    setConfirmOpen(false);
    mutation.mutate({
      tools: form.tools,
      bash: { mode: form.bashMode, patterns: form.bashPatterns },
    });
  }

  return (
    <section className="surface opencode-card opencode-perms" aria-label="opencode 工具权限">
      <header className="opencode-perms-head">
        <div className="opencode-perms-title">
          <span className="opencode-perms-icon">
            <ShieldCheck aria-hidden="true" size={16} />
          </span>
          <div>
            <h2>工具权限</h2>
            <p>控制新建会话中 Agent 可用的工具；保存后对新建会话生效，不影响进行中的会话。</p>
          </div>
        </div>
      </header>

      {permsQuery.isLoading ? <p className="empty-note">正在读取工具权限…</p> : null}
      {permsQuery.isError ? (
        <div className="opencode-status-line" data-tone="error">
          <AlertTriangle aria-hidden="true" size={15} />
          <span>读取工具权限失败</span>
        </div>
      ) : null}

      {data && form ? (
        <>
          <div className="opencode-matrix">
            {grouped.map(({ group, items }) => (
              <div className="opencode-matrix-group" key={group}>
                <span className="opencode-matrix-group-label">
                  {GROUP_LABELS[group] ?? group}
                </span>
                <div className="opencode-matrix-rows">
                  {items.map((item) => (
                    <ToolRow
                      key={item.key}
                      item={item}
                      value={form.tools[item.key] ?? "deny"}
                      onChange={(value) => setToolValue(item.key, value)}
                    />
                  ))}
                </div>
              </div>
            ))}

            <BashRow
              mode={form.bashMode}
              patterns={form.bashPatterns}
              suggestions={data.catalog.bash_suggestions}
              onModeChange={setBashMode}
              onPatternsChange={setBashPatterns}
            />
          </div>

          <footer className="opencode-perms-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={resetToDefaults}
              disabled={mutation.isPending}
            >
              <RotateCcw aria-hidden="true" size={15} />
              恢复默认
            </button>
            <button
              className="button button-primary"
              type="button"
              disabled={!dirty || mutation.isPending}
              onClick={() => setConfirmOpen(true)}
            >
              <Save aria-hidden="true" size={15} />
              {mutation.isPending ? "保存中…" : "保存"}
            </button>
          </footer>
        </>
      ) : null}

      {confirmOpen ? (
        <div className="dialog-backdrop">
          <section
            aria-labelledby="opencode-perms-confirm-title"
            aria-modal="true"
            className="confirm-dialog"
            role="dialog"
          >
            <div className="dialog-icon warning">
              <AlertTriangle aria-hidden="true" size={18} />
            </div>
            <div className="dialog-content">
              <h2 id="opencode-perms-confirm-title">保存工具权限</h2>
              <p>
                新的权限会写入配置，并在<strong>下一次会话初始化</strong>时生效；
                正在进行中的会话不受影响。确认保存？
              </p>
              <div className="dialog-actions">
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => setConfirmOpen(false)}
                >
                  取消
                </button>
                <button className="button button-primary" type="button" onClick={handleSave}>
                  确认保存
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function ToolRow({
  item,
  value,
  onChange,
}: {
  item: OpencodeToolCatalogItem;
  value: OpencodePermissionValue;
  onChange: (value: OpencodePermissionValue) => void;
}) {
  const Icon = TOOL_ICONS[item.key] ?? FileText;
  return (
    <div className="opencode-tool-row" data-openviking={item.openviking ? "true" : undefined}>
      <span className="opencode-tool-icon">
        <Icon aria-hidden="true" size={15} />
      </span>
      <div className="opencode-tool-meta">
        <strong>
          {item.label}
          <code className="opencode-tool-key">{item.key}</code>
        </strong>
        <span>{item.purpose}</span>
      </div>
      <AllowDenyControl label={item.label} value={value} onChange={onChange} />
    </div>
  );
}

function AllowDenyControl({
  label,
  value,
  onChange,
}: {
  label: string;
  value: OpencodePermissionValue;
  onChange: (value: OpencodePermissionValue) => void;
}) {
  return (
    <div
      className="opencode-segmented opencode-segmented-binary"
      data-value={value}
      role="radiogroup"
      aria-label={`${label} 权限`}
    >
      <button
        type="button"
        role="radio"
        aria-checked={value === "allow"}
        data-tone="allow"
        onClick={() => onChange("allow")}
      >
        允许
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={value === "deny"}
        data-tone="deny"
        onClick={() => onChange("deny")}
      >
        拒绝
      </button>
    </div>
  );
}

function BashRow({
  mode,
  patterns,
  suggestions,
  onModeChange,
  onPatternsChange,
}: {
  mode: OpencodeBashMode;
  patterns: string[];
  suggestions: string[];
  onModeChange: (mode: OpencodeBashMode) => void;
  onPatternsChange: (patterns: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function addPattern(raw: string) {
    const value = raw.trim();
    if (!value || patterns.includes(value)) {
      setDraft("");
      return;
    }
    onPatternsChange([...patterns, value]);
    setDraft("");
  }

  function removePattern(target: string) {
    onPatternsChange(patterns.filter((item) => item !== target));
  }

  function fillSuggestions() {
    const merged = [...patterns];
    for (const suggestion of suggestions) {
      if (!merged.includes(suggestion)) {
        merged.push(suggestion);
      }
    }
    onPatternsChange(merged);
  }

  return (
    <div className="opencode-bash-row" data-mode={mode}>
      <div className="opencode-tool-row opencode-tool-row-bash">
        <span className="opencode-tool-icon opencode-tool-icon-bash">
          <Terminal aria-hidden="true" size={15} />
        </span>
        <div className="opencode-tool-meta">
          <strong>
            Shell 命令
            <code className="opencode-tool-key">bash</code>
          </strong>
          <span>执行 shell 命令。白名单可放行 git / ls / rg 等只读检索命令。</span>
        </div>
        <div
          className="opencode-segmented opencode-segmented-tri"
          data-value={mode}
          role="radiogroup"
          aria-label="bash 权限模式"
        >
          <button
            type="button"
            role="radio"
            aria-checked={mode === "allow"}
            data-tone="allow"
            onClick={() => onModeChange("allow")}
          >
            允许
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={mode === "deny"}
            data-tone="deny"
            onClick={() => onModeChange("deny")}
          >
            拒绝
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={mode === "whitelist"}
            data-tone="whitelist"
            onClick={() => onModeChange("whitelist")}
          >
            白名单
          </button>
        </div>
      </div>

      {mode === "whitelist" ? (
        <div className="opencode-terminal" aria-label="bash 命令白名单">
          <div className="opencode-terminal-bar">
            <span className="opencode-terminal-dot" data-dot="r" />
            <span className="opencode-terminal-dot" data-dot="y" />
            <span className="opencode-terminal-dot" data-dot="g" />
            <span className="opencode-terminal-title">allowlist — 仅匹配的命令可执行，其余拒绝</span>
            <button
              type="button"
              className="opencode-terminal-fill"
              onClick={fillSuggestions}
            >
              <Sparkles aria-hidden="true" size={12} />
              填入推荐
            </button>
          </div>
          <div className="opencode-terminal-body">
            {patterns.length === 0 ? (
              <p className="opencode-terminal-empty">
                白名单为空 —— 等价于「拒绝」。添加形如 <code>git *</code> 的命令通配符。
              </p>
            ) : (
              <ul className="opencode-pattern-list">
                {patterns.map((pattern) => (
                  <li key={pattern} className="opencode-pattern-chip">
                    <span className="opencode-pattern-prompt">$</span>
                    <code>{pattern}</code>
                    <button
                      type="button"
                      aria-label={`移除 ${pattern}`}
                      onClick={() => removePattern(pattern)}
                    >
                      <X aria-hidden="true" size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="opencode-pattern-input">
              <span className="opencode-pattern-prompt">$</span>
              <input
                aria-label="添加命令通配符"
                placeholder="git *"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addPattern(draft);
                  }
                }}
              />
              <button
                type="button"
                className="opencode-pattern-add"
                disabled={!draft.trim()}
                onClick={() => addPattern(draft)}
              >
                <Plus aria-hidden="true" size={13} />
                添加
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
