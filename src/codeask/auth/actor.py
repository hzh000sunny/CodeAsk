"""Request actor resolved by identity middleware."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Actor:
    subject_id: str
    display_name: str
    role: str
    authenticated: bool
    user_id: str | None = None
    username: str | None = None
    anonymous_subject_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
