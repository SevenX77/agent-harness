from __future__ import annotations

from pathlib import Path


def test_engine_src_no_longer_emits_v21_error_codes() -> None:
    src_root = Path(__file__).parents[2] / "src" / "graph_agent"
    legacy_prefix = "F-" + "v21-"
    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if f"[{legacy_prefix}" in text or legacy_prefix in text:
            offenders.append(str(path.relative_to(src_root)))

    assert offenders == []
