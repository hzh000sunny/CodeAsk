"""Feature permission helpers."""

from codeask.auth.actor import Actor


def can_manage_feature(actor: Actor, *, feature_admin_user_ids: set[str]) -> bool:
    return actor.is_admin or (actor.user_id is not None and actor.user_id in feature_admin_user_ids)


def can_manage_feature_admins(actor: Actor) -> bool:
    return actor.is_admin
