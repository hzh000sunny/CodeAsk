"""CodeAsk primary data to OpenViking URI mapping."""

from urllib.parse import quote

_ROOT = "viking://resources/codeask"


def _segment(value: str) -> str:
    return quote(value.strip("/"), safe="-_.")


def feature_readme_uri(feature_slug: str) -> str:
    return f"{_ROOT}/features/{_segment(feature_slug)}/README.md"


def wiki_doc_uri(feature_slug: str, relative_path: str) -> str:
    parts = [_segment(part) for part in relative_path.strip("/").split("/") if part]
    return f"{_ROOT}/features/{_segment(feature_slug)}/knowledge-base/{'/'.join(parts)}"


def report_uri(feature_slug: str, filename: str) -> str:
    return (
        f"{_ROOT}/features/{_segment(feature_slug)}/problem-reports/verified/{_segment(filename)}"
    )


def repo_uri(repo_slug: str) -> str:
    return f"{_ROOT}/repos/{_segment(repo_slug)}/"
