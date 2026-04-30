"""Extract engineering precision signals from wiki text."""

import re

_ERROR_CODE_RE = re.compile(r"\b(?:ERR|ERROR|E)_[A-Z][A-Z0-9_]{2,}\b")
_SQLSTATE_RE = re.compile(r"\bSQLSTATE\s+[0-9A-Z]{5}\b")
_EXCEPTION_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Exception|Error)\b")
_ROUTE_RE = re.compile(r"/api(?:/[A-Za-z0-9_\-]+)+")
_CONFIG_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*){2,}\b")
_CLASS_SYMBOL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z0-9]+){1,}\b")
_FN_SYMBOL_RE = re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+){1,}\b")
_FILE_PATH_RE = re.compile(
    r"\b(?:[A-Za-z0-9_\-]+/)+[A-Za-z0-9_\-]+"
    r"\.(?:py|ts|tsx|js|jsx|java|go|rs|rb|kt|cs|cpp|c|h|hpp|sql|md|yaml|yml|toml|json)\b"
)

_EMPTY_SIGNALS: dict[str, list[str]] = {
    "error_codes": [],
    "exception_names": [],
    "routes": [],
    "config_keys": [],
    "symbols": [],
    "file_paths": [],
}


def _dedup(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def extract_signals(text: str) -> dict[str, list[str]]:
    """Return ordered unique engineering signals grouped by bucket."""
    if not text:
        return {key: [] for key in _EMPTY_SIGNALS}

    error_codes = _dedup(_ERROR_CODE_RE.findall(text) + _SQLSTATE_RE.findall(text))
    exception_names = _dedup(_EXCEPTION_RE.findall(text))
    routes = _dedup(_ROUTE_RE.findall(text))
    config_keys = _dedup(_CONFIG_KEY_RE.findall(text))
    symbols = _dedup(_CLASS_SYMBOL_RE.findall(text) + _FN_SYMBOL_RE.findall(text))
    file_paths = _dedup(_FILE_PATH_RE.findall(text))
    symbols = [symbol for symbol in symbols if symbol not in exception_names]

    return {
        "error_codes": error_codes,
        "exception_names": exception_names,
        "routes": routes,
        "config_keys": config_keys,
        "symbols": symbols,
        "file_paths": file_paths,
    }
