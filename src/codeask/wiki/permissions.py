"""Permission helpers for wiki feature and node operations."""

from codeask.db.models import Feature
from codeask.wiki.actor import WikiActor


def can_read_feature(actor: WikiActor, feature: Feature) -> bool:
    return True


def can_write_feature(actor: WikiActor, feature: Feature) -> bool:
    return actor.is_admin or actor.subject_id == feature.owner_subject_id


def can_admin_feature(actor: WikiActor, feature: Feature) -> bool:
    return actor.is_admin
