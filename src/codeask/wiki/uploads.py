"""Upload validation helpers for wiki documents and attachments."""

from pathlib import Path


class UnsupportedMime(ValueError):
    """Raised when an upload looks like a disallowed binary payload."""


def validate_upload(path: Path, declared_mime: str | None = None) -> None:
    """Reject obviously executable payloads before parsing.

    The v1.0 boundary only needs a light-weight guardrail: if the file starts
    with a PE header, treat it as an unsupported binary upload even when the
    extension or declared mime type claims it is a document.
    """

    data = path.read_bytes()
    if data.startswith(b"MZ"):
        raise UnsupportedMime("unsupported file content: executable payload")
