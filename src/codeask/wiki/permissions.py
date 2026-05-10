"""Permission helpers for wiki feature and node operations."""

from codeask.db.models import Feature
from codeask.wiki.actor import WikiActor


def can_read_feature(actor: WikiActor, feature: Feature) -> bool:
    return True


def can_write_feature(actor: WikiActor, feature: Feature) -> bool:
    return actor.is_admin or feature.id in actor.feature_admin_feature_ids


def can_admin_feature(actor: WikiActor, feature: Feature) -> bool:
    del feature
    return actor.is_admin


def can_maintain_feature(actor: WikiActor, feature: Feature) -> bool:
    return can_write_feature(actor, feature)
