"""Static check: business code must not hard-code 0.0.0.0."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PATTERN = re.compile(r'["\']0\.0\.0\.0["\']')


def test_no_business_zero_zero_zero_zero() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if PATTERN.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Hard-coded 0.0.0.0 found in src/. Default bind must be 127.0.0.1:\n  "
        + "\n  ".join(offenders)
    )
