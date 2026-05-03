"""Wiki actor model used by permission checks."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WikiActor:
    subject_id: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
