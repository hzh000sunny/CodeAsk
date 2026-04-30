"""L0-L6 prompt assembly for agent stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeask.agent.state import AgentState
from codeask.llm.types import LLMMessage, TextBlock

L0_GLOBAL_RULES = """L0_GLOBAL_RULES
You are CodeAsk, a private R&D question-answering agent.
Answer only from collected knowledge, code evidence, or explicit uncertainty.
Use tools only through the provided tool protocol and keep evidence ids stable.
"""


def _empty_paths() -> list[str]:
    return []


def _empty_feature_digests() -> list[FeatureDigest]:
    return []


def _empty_repo_bindings() -> list[RepoBinding]:
    return []


def _empty_knowledge_hits() -> list[KnowledgeHit]:
    return []


def _empty_messages() -> list[LLMMessage]:
    return []


def _empty_attachment_summaries() -> list[dict[str, Any]]:
    return []


def _empty_extra_context() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class FeatureDigest:
    feature_id: int
    summary_text: str | None = None
    navigation_index: str | None = None
    feature_skill: str | None = None


@dataclass(frozen=True)
class RepoBinding:
    repo_id: str
    commit_sha: str
    paths: list[str] = field(default_factory=_empty_paths)


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    title: str
    summary: str
    report_high_priority: bool = False


@dataclass(frozen=True)
class PromptContext:
    user_question: str
    feature_digests: list[FeatureDigest] = field(default_factory=_empty_feature_digests)
    global_skill: str | None = None
    repo_bindings: list[RepoBinding] = field(default_factory=_empty_repo_bindings)
    pre_retrieval_hits: list[KnowledgeHit] = field(default_factory=_empty_knowledge_hits)
    turn_history: list[LLMMessage] = field(default_factory=_empty_messages)
    log_analysis: dict[str, Any] | None = None
    attachment_summaries: list[dict[str, Any]] = field(default_factory=_empty_attachment_summaries)
    extra_context: dict[str, Any] = field(default_factory=_empty_extra_context)


def assemble_messages(stage: AgentState, ctx: PromptContext) -> list[LLMMessage]:
    system_text = "\n\n".join(
        [
            L0_GLOBAL_RULES,
            _l1_stage(stage),
            _l2_feature_context(ctx),
            _l3_repo_context(ctx),
        ]
    )
    user_text = "\n\n".join([_l4_pre_retrieval(ctx), _l6_current_input(ctx)])
    return [
        LLMMessage(role="system", content=[TextBlock(type="text", text=system_text)]),
        *ctx.turn_history,
        LLMMessage(role="user", content=[TextBlock(type="text", text=user_text)]),
    ]


def _l1_stage(stage: AgentState) -> str:
    return "\n".join(
        [
            "L1_STAGE",
            f"stage={stage.value}",
            "Follow the current stage objective and stop when its exit condition is met.",
        ]
    )


def _l2_feature_context(ctx: PromptContext) -> str:
    lines = ["L2_FEATURE_CONTEXT"]
    if ctx.global_skill:
        lines.append(f"global_skill: {ctx.global_skill}")
    if not ctx.feature_digests:
        lines.append("features: none selected")
        return "\n".join(lines)

    for digest in ctx.feature_digests:
        lines.append(f"feature_id={digest.feature_id}")
        if digest.summary_text:
            lines.append(f"summary: {digest.summary_text}")
        if digest.navigation_index:
            lines.append(f"navigation_index: {digest.navigation_index}")
        if digest.feature_skill:
            lines.append(f"feature_skill: {digest.feature_skill}")
    return "\n".join(lines)


def _l3_repo_context(ctx: PromptContext) -> str:
    lines = ["L3_REPO_CONTEXT"]
    if not ctx.repo_bindings:
        lines.append("repos: none")
        return "\n".join(lines)
    for binding in ctx.repo_bindings:
        path_hint = ",".join(binding.paths) if binding.paths else "-"
        lines.append(f"{binding.repo_id}@{binding.commit_sha} paths={path_hint}")
    return "\n".join(lines)


def _l4_pre_retrieval(ctx: PromptContext) -> str:
    lines = ["L4_PRE_RETRIEVAL"]
    if not ctx.pre_retrieval_hits:
        lines.append("hits: none")
        return "\n".join(lines)
    for hit in ctx.pre_retrieval_hits:
        priority = " REPORT_HIGH_PRIORITY" if hit.report_high_priority else ""
        lines.append(f"[{hit.source}{priority}] {hit.title}: {hit.summary}")
    return "\n".join(lines)


def _l6_current_input(ctx: PromptContext) -> str:
    lines = ["L6_CURRENT_INPUT", f"question: {ctx.user_question}"]
    if ctx.log_analysis:
        lines.append(f"log_analysis: {ctx.log_analysis}")
    if ctx.attachment_summaries:
        lines.append(f"attachment_summaries: {ctx.attachment_summaries}")
    if ctx.extra_context:
        lines.append(f"extra_context: {ctx.extra_context}")
    return "\n".join(lines)
