"""CodeAsk primary data to OpenViking URI mapping."""

from urllib.parse import quote

_ROOT = "viking://resources/codeask"


def _segment(value: str) -> str:
    return quote(value.strip("/"), safe="-_.")


def wiki_root_uri() -> str:
    return f"{_ROOT}/wiki"


def wiki_feature_uri(feature_slug: str) -> str:
    return f"{wiki_root_uri()}/{_segment(feature_slug)}"


def code_root_uri() -> str:
    return f"{_ROOT}/code"


def code_repo_uri(repo_slug: str) -> str:
    return f"{code_root_uri()}/{_segment(repo_slug)}/"
