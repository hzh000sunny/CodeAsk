"""Tests for feature permission helpers."""

from codeask.auth.actor import Actor
from codeask.features.permissions import can_manage_feature, can_manage_feature_admins


def test_admin_can_manage_every_feature() -> None:
    actor = Actor(
        subject_id="admin",
        display_name="Admin",
        role="admin",
        authenticated=True,
        user_id="user_admin",
        username="admin",
    )

    assert can_manage_feature(actor, feature_admin_user_ids=set())
    assert can_manage_feature_admins(actor)


def test_feature_admin_can_manage_assigned_feature() -> None:
    actor = Actor(
        subject_id="user_a",
        display_name="Alice",
        role="member",
        authenticated=True,
        user_id="user_a",
        username="Alice",
    )

    assert can_manage_feature(actor, feature_admin_user_ids={"user_a"})
    assert not can_manage_feature_admins(actor)


def test_anonymous_cannot_manage_feature() -> None:
    actor = Actor(
        subject_id="client_a",
        display_name="client_a",
        role="member",
        authenticated=False,
    )

    assert not can_manage_feature(actor, feature_admin_user_ids=set())
    assert not can_manage_feature_admins(actor)
