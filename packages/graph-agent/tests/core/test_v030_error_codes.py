from __future__ import annotations

from pathlib import Path


def test_v21_error_codes_are_retired_from_src_and_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    scanned_roots = [root / "src", root / "tests"]
    retired_prefix = "F-" + "v21-"
    offenders: list[str] = []
    for scanned_root in scanned_roots:
        for path in scanned_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            if retired_prefix in text:
                offenders.append(path.relative_to(root).as_posix())

    assert offenders == []
