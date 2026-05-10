"""Tests for auth session helpers."""

from datetime import UTC, datetime, timedelta

from codeask.auth.sessions import (
    create_session_token,
    hash_session_token,
    session_expiry,
    should_renew,
)


def test_session_token_hash_is_stable_and_does_not_equal_token() -> None:
    token = create_session_token()

    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != token


def test_session_expiry_uses_ttl_days() -> None:
    now = datetime(2026, 5, 10, 8, 0, tzinfo=UTC)

    assert session_expiry(now=now, ttl_days=7) == now + timedelta(days=7)


def test_should_renew_when_remaining_lifetime_enters_second_half() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    expires = now + timedelta(days=2)
    last_seen = now - timedelta(minutes=5)

    assert should_renew(now=now, expires_at=expires, last_seen_at=last_seen, ttl_days=7)


def test_should_not_renew_when_remaining_lifetime_is_still_large() -> None:
    now = datetime(2026, 5, 10, tzinfo=UTC)
    expires = now + timedelta(days=6)
    last_seen = now - timedelta(days=4)

    assert not should_renew(now=now, expires_at=expires, last_seen_at=last_seen, ttl_days=7)
