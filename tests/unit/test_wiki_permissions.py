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


def test_feature_owner_cannot_write_without_feature_admin_grant() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="owner@dev-1", role="member")
    assert can_write_feature(actor, feature) is False


def test_feature_admin_can_write_assigned_feature() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(
        subject_id="user_owner",
        role="member",
        user_id="user_owner",
        authenticated=True,
        feature_admin_feature_ids=frozenset({1}),
    )
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


def test_non_feature_admin_member_cannot_write() -> None:
    feature = Feature(
        id=1,
        name="Payments",
        slug="payments",
        owner_subject_id="owner@dev-1",
    )
    actor = WikiActor(subject_id="viewer@dev-1", role="member")
    assert can_write_feature(actor, feature) is False
