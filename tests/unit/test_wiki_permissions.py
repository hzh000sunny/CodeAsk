"""Unit tests for wiki actor permissions."""

from codeask.db.models import Feature
from codeask.wiki.actor import WikiActor
from codeask.wiki.permissions import can_read_feature, can_write_feature


def test_any_viewer_can_read_feature() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="viewer@dev-1", role="member")
    assert can_read_feature(actor, feature) is True


def test_feature_owner_can_write() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="owner@dev-1", role="member")
    assert can_write_feature(actor, feature) is True


def test_admin_can_write_any_feature() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="admin", role="admin")
    assert can_write_feature(actor, feature) is True


def test_non_owner_member_can_write_in_v1_0_1() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="viewer@dev-1", role="member")
    assert can_write_feature(actor, feature) is True
