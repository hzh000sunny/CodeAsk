import type { AgentEvent } from "../../../types/sse";

export type ActionTraceKind =
  | "analysis"
  | "retrieval"
  | "tool_call"
  | "tool_result"
  | "evidence"
  | "clarification"
  | "assistant_action"
  | "diagnostic"
  | "warning"
  | "error";

export interface EvidenceRef {
  type?: string;
  title?: string | null;
  path?: string | null;
  node_id?: number | null;
  report_id?: number | null;
  attachment_id?: string | null;
  repo_id?: string | number | null;
  ref?: string | null;
  commit?: string | null;
  line?: number | null;
  metadata?: Record<string, unknown>;
}

export interface ActionTraceEvent {
  id: string;
  kind: ActionTraceKind | string;
  title: string;
  detail: string;
  detailMarkdown?: string;
  turnId?: string;
  occurredAt?: string;
  status?: "running" | "success" | "error" | "info";
  data?: Record<string, unknown>;
  evidenceRefs?: EvidenceRef[];
}

export function actionTraceFromAgentEvent(
  event: AgentEvent,
): ActionTraceEvent | null {
  if (event.type === "llm_input") {
    return {
      id: `llm_input_${numberValue(event.data.round) ?? Date.now()}`,
      kind: "diagnostic",
      title: "模型输入审计",
      detail: llmInputDetail(event.data),
      detailMarkdown: llmInputMarkdown(event.data),
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }

  if (event.type === "retrieval_context") {
    const featureCandidates = objectArrayData(event.data.feature_candidates);
    const wikiHits = objectArrayData(event.data.wiki_hits);
    const reportHits = objectArrayData(event.data.report_hits);
    const total = featureCandidates.length + wikiHits.length + reportHits.length;
    return {
      id: `retrieval_${Date.now()}`,
      kind: "retrieval",
      title: total > 0 ? `已准备 ${total} 条上下文` : "上下文已准备",
      detail:
        [
          featureCandidates.length
            ? `${featureCandidates.length} 个候选特性`
            : null,
          wikiHits.length ? `${wikiHits.length} 条 Wiki` : null,
          reportHits.length ? `${reportHits.length} 份报告` : null,
        ]
          .filter(Boolean)
          .join(" · ") || "模型将基于当前会话和可用知识回答",
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }

  if (event.type === "tool_call") {
    const toolName =
      stringValue(event.data.tool_name) ?? stringValue(event.data.name) ?? "unknown";
    return {
      id: `tool_call_${stringValue(event.data.tool_call_id) ?? stringValue(event.data.id) ?? Date.now()}`,
      kind: "tool_call",
      title: `准备使用 ${toolDisplayName(toolName)}`,
      detail: toolCallDetail(event.data),
      status: "running",
      data: event.data,
      evidenceRefs: [],
    };
  }

  if (event.type === "tool_result") {
    const toolName =
      stringValue(event.data.tool_name) ?? stringValue(event.data.name) ?? "unknown";
    const ok = event.data.ok === true || recordValue(event.data.result).ok === true;
    const failed =
      event.data.ok === false || recordValue(event.data.result).ok === false;
    const title = toolName === "unknown" ? "工具结果" : toolDisplayName(toolName);
    return {
      id: `tool_result_${stringValue(event.data.tool_call_id) ?? stringValue(event.data.id) ?? Date.now()}`,
      kind: "tool_result",
      title: `${title}${failed ? "失败" : "完成"}`,
      detail: toolResultDetail(event.data),
      status: failed ? "error" : ok ? "success" : "info",
      data: event.data,
      evidenceRefs: evidenceRefsFromValue(event.data.evidence_refs),
    };
  }

  if (event.type === "evidence") {
    const refs = evidenceRefsFromValue(event.data.evidence_refs);
    const legacyItem = recordValue(event.data.item);
    const legacyDetail = legacyEvidenceDetail(legacyItem);
    return {
      id:
        stringValue(legacyItem.id) ??
        `evidence_${refs.map((ref) => ref.node_id ?? ref.path).join("_") || Date.now()}`,
      kind: "evidence",
      title:
        refs.length > 0
          ? `收集到 ${refs.length} 条证据`
          : `证据：${stringValue(legacyItem.title) ?? "已收集"}`,
      detail:
        refs
          .map((ref) => evidenceLabel(ref))
          .filter(Boolean)
          .slice(0, 2)
          .join(" · ") ||
        legacyDetail ||
        compactJson(legacyItem),
      detailMarkdown: legacyEvidenceMarkdown(legacyItem),
      status: "success",
      data: event.data,
      evidenceRefs: refs,
    };
  }

  if (event.type === "needs_clarification" || event.type === "ask_user") {
    return {
      id: stringValue(event.data.ask_id) ?? `clarification_${Date.now()}`,
      kind: "clarification",
      title: "需要补充信息",
      detail: stringValue(event.data.question) ?? "模型需要更多上下文才能继续",
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }

  if (event.type === "reasoning_observed") {
    return {
      id: `reasoning_observed_${Date.now()}`,
      kind: "diagnostic",
      title: "模型推理已隔离",
      detail:
        [
          stringValue(event.data.field) ? `字段 ${stringValue(event.data.field)}` : null,
          typeof event.data.length === "number" ? `长度 ${event.data.length}` : null,
          typeof event.data.chunks === "number" ? `分片 ${event.data.chunks}` : null,
          event.data.redacted === true ? "redacted" : null,
        ]
          .filter(Boolean)
          .join(" · ") || "已收到结构化 reasoning 事件，未进入聊天正文",
      status: "info",
      data: {
        field: event.data.field,
        length: event.data.length,
        chunks: event.data.chunks,
        redacted: event.data.redacted,
        raw_reasoning_used: false,
      },
      evidenceRefs: [],
    };
  }

  if (event.type === "reasoning_leak_detected") {
    return {
      id: `reasoning_leak_detected_${Date.now()}`,
      kind: "warning",
      title: "检测到推理泄漏",
      detail:
        event.data.masked === true
          ? "疑似推理文本已在界面遮蔽，需检查上游模型服务是否输出结构化 reasoning"
          : "疑似推理文本已记录诊断，当前模式未遮蔽显示",
      status: "info",
      data: {
        marker: event.data.marker,
        mode: event.data.mode,
        leakedLength: event.data.leakedLength,
        masked: event.data.masked,
      },
      evidenceRefs: [],
    };
  }

  if (event.type === "assistant_action") {
    return {
      id: `assistant_action_${Date.now()}`,
      kind: "assistant_action",
      title: stringValue(event.data.action) ?? "模型建议操作",
      detail: stringValue(event.data.summary) ?? compactJson(event.data),
      status:
        event.data.required_confirmation === true ? "info" : "success",
      data: event.data,
      evidenceRefs: [],
    };
  }

  if (event.type === "error") {
    return {
      id: `error_${Date.now()}`,
      kind: "error",
      title: stringValue(event.data.code) ?? "运行失败",
      detail: stringValue(event.data.message) ?? "Agent 运行失败",
      status: "error",
      data: event.data,
      evidenceRefs: [],
    };
  }

  return legacyActionTraceFromEvent(event);
}

export function actionTraceKindLabel(kind: ActionTraceKind | string) {
  if (kind === "wiki_scope") {
    return "Wiki";
  }
  if (kind === "retrieval") {
    return "上下文";
  }
  if (kind === "tool_call") {
    return "工具";
  }
  if (kind === "tool_result") {
    return "结果";
  }
  if (kind === "evidence") {
    return "证据";
  }
  if (kind === "clarification") {
    return "补充";
  }
  if (kind === "assistant_action") {
    return "建议";
  }
  if (kind === "diagnostic") {
    return "诊断";
  }
  if (kind === "warning") {
    return "提醒";
  }
  return "错误";
}

export function evidenceLabel(ref: EvidenceRef) {
  return (
    ref.title ??
    ref.path ??
    ref.attachment_id ??
    ref.ref ??
    (ref.node_id ? `Wiki #${ref.node_id}` : null) ??
    (ref.report_id ? `报告 #${ref.report_id}` : null) ??
    "未命名证据"
  );
}

function legacyActionTraceFromEvent(event: AgentEvent): ActionTraceEvent | null {
  if (event.type === "scope_detection") {
    return {
      id: `legacy_scope_${Date.now()}`,
      kind: "retrieval",
      title: "已识别上下文线索",
      detail: stringValue(event.data.reason) ?? "模型已整理可能相关的功能线索",
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }
  if (event.type === "wiki_scope_resolution") {
    const featureId = intValue(event.data.feature_id);
    const defaults = objectArrayData(event.data.defaults);
    const matches = objectArrayData(event.data.matches);
    const labels = defaults
      .map((item) => stringValue(item.label) ?? stringValue(item.path))
      .filter(Boolean)
      .slice(0, 2);
    return {
      id: `legacy_wiki_scope_${Date.now()}`,
      kind: "wiki_scope",
      title:
        labels.length > 0 ? `Wiki 范围：${labels.join("、")}` : "Wiki 范围",
      detail:
        matches.length > 0
          ? `显式命中 ${matches.length} 个节点，默认范围 ${defaults.length} 个`
          : `默认范围 ${defaults.length} 个`,
      detailMarkdown: wikiScopeMarkdown(
        featureId,
        stringValue(event.data.query),
        defaults,
        matches,
      ),
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }
  if (event.type === "sufficiency_judgement") {
    return {
      id: `legacy_evaluation_${Date.now()}`,
      kind: "assistant_action",
      title: "已评估当前证据",
      detail: stringValue(event.data.reason) ?? "模型已判断当前上下文是否支持回答",
      status: "info",
      data: event.data,
      evidenceRefs: [],
    };
  }
  return null;
}

function toolCallDetail(data: Record<string, unknown>) {
  const args = recordValue(data.arguments_summary) ?? recordValue(data.arguments);
  const parts = [
    stringValue(data.reason),
    stringValue(args.query) ? `query=${stringValue(args.query)}` : null,
    stringValue(args.path),
    stringValue(args.ref) ? `ref=${stringValue(args.ref)}` : null,
  ].filter(Boolean);
  return parts.join(" · ") || truncateText(compactJson(args), 160) || "等待工具返回";
}

function toolResultDetail(data: Record<string, unknown>) {
  const result = recordValue(data.result);
  const resultData = recordValue(result.data);
  const versionInfo = recordValue(data.version_info) ?? recordValue(result.version_info);
  const summary =
    stringValue(data.summary) ??
    stringValue(result.summary) ??
    stringValue(resultData.summary) ??
    stringValue(result.message);
  const hits = Array.isArray(resultData.hits) ? `${resultData.hits.length} 条命中` : null;
  const featureIds = intArrayValue(versionInfo.feature_ids);
  const repo = codeRepoLabel(versionInfo);
  const warnings = Array.isArray(data.warnings)
    ? data.warnings.filter((item): item is string => typeof item === "string")
    : [];
  const itemsCount = numberValue(data.items_count);
  const parts = [
    summary,
    scopeSourceLabel(stringValue(versionInfo.scope_source)),
    featureIds.length > 0 ? `特性 ${featureIds.join(", ")}` : null,
    repo,
    hits,
    itemsCount !== null ? `结果 ${itemsCount} 条` : null,
    warnings.length > 0 ? `提醒 ${warnings.length} 条` : null,
    data.truncated === true ? "结果已截断" : null,
    stringValue(data.error_type) ? `错误：${stringValue(data.error_type)}` : null,
  ].filter(Boolean);
  return parts.join(" · ") || compactJson(data);
}

function evidenceRefsFromValue(value: unknown): EvidenceRef[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => recordValue(item))
    .filter((item) => Object.keys(item).length > 0)
    .map((item) => ({
      ...item,
      metadata: recordValue(item.metadata),
    }));
}

function legacyEvidenceMarkdown(item: Record<string, unknown>) {
  const featureId = intValue(item.feature_id);
  const nodeId = intValue(item.node_id);
  if (featureId === null || nodeId === null) {
    return undefined;
  }
  const label = escapeMarkdown(
    stringValue(item.path) ?? stringValue(item.title) ?? "查看证据",
  );
  const params = new URLSearchParams({
    feature: String(featureId),
    node: String(nodeId),
  });
  const headingPath = stringValue(item.heading_path);
  if (headingPath) {
    params.set("heading", headingPath);
  }
  return `[${label}](#/wiki?${params.toString()})`;
}

function legacyEvidenceDetail(item: Record<string, unknown>) {
  return [
    stringValue(item.title),
    stringValue(item.source),
    stringValue(item.locator),
    stringValue(item.path),
    stringValue(item.heading_path),
  ]
    .filter(Boolean)
    .join(" · ");
}

function wikiScopeMarkdown(
  featureId: number | null,
  query: string | null,
  defaults: Record<string, unknown>[],
  matches: Record<string, unknown>[],
) {
  const sections: string[] = [];
  if (query) {
    sections.push(`**检索问题**\n${query}`);
  }
  if (defaults.length > 0) {
    sections.push(
      `**默认范围**\n${defaults
        .map((item) => `- ${wikiScopeItemLabel(item, featureId)}`)
        .join("\n")}`,
    );
  }
  if (matches.length > 0) {
    sections.push(
      `**显式命中**\n${matches
        .map((item) => {
          const extras = [
            stringValue(item.match_reason),
            stringValue(item.matched_phrase)
              ? `“${stringValue(item.matched_phrase)}”`
              : null,
          ]
            .filter(Boolean)
            .join(" · ");
          return `- ${wikiScopeItemLabel(item, featureId)}${
            extras ? ` · ${extras}` : ""
          }`;
        })
        .join("\n")}`,
    );
  }
  return sections.join("\n\n");
}

function wikiScopeItemLabel(
  item: Record<string, unknown>,
  featureId: number | null,
) {
  const path = stringValue(item.path) ?? stringValue(item.label) ?? "未命名节点";
  const itemFeatureId = intValue(item.feature_id) ?? featureId;
  const nodeId = intValue(item.node_id);
  if (itemFeatureId !== null && nodeId !== null) {
    return `[${escapeMarkdown(path)}](#/wiki?feature=${itemFeatureId}&node=${nodeId})`;
  }
  return escapeMarkdown(path);
}

function toolDisplayName(name: string) {
  const labels: Record<string, string> = {
    ask_user: "补充信息",
    inspect_repo_tree: "仓库目录",
    list_code_repos: "代码仓库",
    list_code_paths: "代码路径",
    list_session_attachments: "会话数据",
    load_analysis_policy: "分析策略",
    propose_report: "报告建议",
    read_code_file: "代码文件",
    read_report: "问题报告",
    read_session_attachment: "会话数据",
    read_wiki_node: "Wiki",
    search_code: "代码搜索",
    search_reports: "报告搜索",
    search_wiki: "Wiki 搜索",
  };
  return labels[name] ?? name;
}

function objectArrayData(value: unknown) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(
    (item): item is Record<string, unknown> =>
      typeof item === "object" && item !== null && !Array.isArray(item),
  );
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function llmInputDetail(data: Record<string, unknown>) {
  const round = numberValue(data.round);
  const messages = numberValue(data.messages_count);
  const tools = numberValue(data.tools_count);
  const contextSize = numberValue(data.context_size_chars);
  return [
    round !== null ? `第 ${round} 轮` : null,
    messages !== null ? `${messages} 条消息` : null,
    tools !== null ? `${tools} 个工具` : null,
    contextSize !== null ? `上下文 ${Math.max(1, Math.floor(contextSize / 1024))}k` : null,
  ]
    .filter(Boolean)
    .join(" · ") || "模型请求前的公开输入摘要";
}

function llmInputMarkdown(data: Record<string, unknown>) {
  const sections: string[] = [];
  const toolNames = Array.isArray(data.tool_names)
    ? data.tool_names.filter((item): item is string => typeof item === "string")
    : [];
  if (toolNames.length > 0) {
    sections.push(`**可用工具**\n${toolNames.map((name) => `- ${escapeMarkdown(toolDisplayName(name))} (${escapeMarkdown(name)})`).join("\n")}`);
  }

  const recentToolResults = objectArrayData(data.recent_tool_results);
  if (recentToolResults.length > 0) {
    sections.push(
      `**最近工具结果**\n${recentToolResults.map(toolResultAuditLine).join("\n")}`,
    );
  }
  return sections.join("\n\n");
}

function toolResultAuditLine(item: Record<string, unknown>) {
  const tool = stringValue(item.tool) ?? "unknown";
  const summary = stringValue(item.summary);
  const itemsCount = numberValue(item.items_count);
  const repos = objectArrayData(item.repos);
  const head = [
    `- ${escapeMarkdown(toolDisplayName(tool))}`,
    summary ? `：${escapeMarkdown(summary)}` : "",
    itemsCount !== null ? ` · ${itemsCount} 条结果` : "",
  ].join("");
  if (repos.length === 0) {
    return head;
  }
  return `${head}\n${repos
    .map((repo) => {
      const repoName = stringValue(repo.repo_name) ?? "未命名仓库";
      const repoId = stringValue(repo.repo_id);
      return `  - ${escapeMarkdown(repoName)}${repoId ? ` (${escapeMarkdown(repoId)})` : ""}`;
    })
    .join("\n")}`;
}

function intValue(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function intArrayValue(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is number => Number.isInteger(item))
    : [];
}

function scopeSourceLabel(value: string | null) {
  if (value === "feature_scope") {
    return "特性范围";
  }
  if (value === "explicit_user_repo") {
    return "用户显式仓库";
  }
  return value;
}

function codeRepoLabel(versionInfo: Record<string, unknown>) {
  const repoName = stringValue(versionInfo.repo_name);
  const repoId = stringValue(versionInfo.repo_id);
  if (repoName && repoId) {
    return `${repoName}(${repoId})`;
  }
  return repoName ?? repoId;
}

function compactJson(value: unknown) {
  if (value === undefined || value === null) {
    return "-";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function truncateText(value: string | null, maxLength = 120) {
  if (!value) {
    return null;
  }
  return value.length <= maxLength
    ? value
    : `${value.slice(0, maxLength - 1)}...`;
}

function escapeMarkdown(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/\[/g, "\\[").replace(/\]/g, "\\]");
}
