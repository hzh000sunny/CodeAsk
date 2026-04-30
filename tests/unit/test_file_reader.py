"""FileReader read_segment tests."""

from pathlib import Path

import pytest

from codeask.code_index.file_reader import FileReader, FileReadError


def _make(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [f"line-{i}\n" for i in range(1, 51)]
    (root / "f.py").write_text("".join(lines))
    (root / "binary.bin").write_bytes(b"\x00\x01\x02bad\x00\xff")


def test_read_full_range(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    segment = reader.read_segment(base=tmp_path, rel_path="f.py", line_range=(1, 5))
    assert segment.start_line == 1
    assert segment.end_line == 5
    assert segment.text == "line-1\nline-2\nline-3\nline-4\nline-5\n"


def test_clamp_to_eof(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    segment = reader.read_segment(base=tmp_path, rel_path="f.py", line_range=(48, 9999))
    assert segment.start_line == 48
    assert segment.end_line == 50
    assert segment.text.count("\n") == 3


def test_truncate_by_max_bytes(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=20)
    segment = reader.read_segment(base=tmp_path, rel_path="f.py", line_range=(1, 50))
    assert segment.truncated is True
    assert len(segment.text.encode("utf-8")) <= 20


def test_path_escape_rejected(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        reader.read_segment(base=tmp_path, rel_path="../etc/passwd", line_range=(1, 5))


def test_missing_file_raises(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        reader.read_segment(base=tmp_path, rel_path="not-here.py", line_range=(1, 5))


def test_invalid_range(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        reader.read_segment(base=tmp_path, rel_path="f.py", line_range=(0, 5))
    with pytest.raises(FileReadError):
        reader.read_segment(base=tmp_path, rel_path="f.py", line_range=(5, 1))


def test_binary_file_rejected(tmp_path: Path) -> None:
    _make(tmp_path)
    reader = FileReader(max_bytes=10_000)
    with pytest.raises(FileReadError):
        reader.read_segment(base=tmp_path, rel_path="binary.bin", line_range=(1, 5))
