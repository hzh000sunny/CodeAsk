"""Login-session token helpers."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry(now: datetime | None = None, ttl_days: int = 7) -> datetime:
    current = now or datetime.now(UTC)
    return current + timedelta(days=ttl_days)


def should_renew(
    *, now: datetime, expires_at: datetime, last_seen_at: datetime, ttl_days: int
) -> bool:
    del last_seen_at
    ttl = timedelta(days=ttl_days)
    if expires_at <= now:
        return False
    return expires_at - now <= ttl / 2
