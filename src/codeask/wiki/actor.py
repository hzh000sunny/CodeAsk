"""Wiki actor model used by permission checks."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class WikiActor:
    subject_id: str
    role: str
    user_id: str | None = None
    authenticated: bool = False
    feature_admin_feature_ids: frozenset[int] = field(default_factory=lambda: frozenset[int]())

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
