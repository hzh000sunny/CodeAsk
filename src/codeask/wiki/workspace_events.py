"""Commit-after events for maintaining the wiki workspace projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

WikiWorkspaceEventKind = Literal[
    "document_published",
    "feature_created",
    "node_created",
    "node_moved",
    "node_deleted",
    "node_restored",
    "feature_metadata_changed",
    "feature_archived",
    "feature_restored",
    "report_projection_changed",
]

PENDING_WIKI_WORKSPACE_EVENTS = "pending_wiki_workspace_events"


@dataclass(frozen=True, slots=True)
class WikiWorkspaceEvent:
    feature_slug: str
    kind: WikiWorkspaceEventKind
    feature_id: int | None = None
    space_id: int | None = None
    node_id: int | None = None
    document_id: int | None = None
    old_path: str | None = None
    new_path: str | None = None
    affected_node_ids: tuple[int, ...] = ()
    report_id: int | None = None


def stash_pending_wiki_workspace_event(
    session: AsyncSession,
    event: WikiWorkspaceEvent,
) -> None:
    pending_raw = session.info.get(PENDING_WIKI_WORKSPACE_EVENTS)
    if isinstance(pending_raw, list):
        pending = cast(list[WikiWorkspaceEvent], pending_raw)
    else:
        pending = []
        session.info[PENDING_WIKI_WORKSPACE_EVENTS] = pending
    pending.append(event)
