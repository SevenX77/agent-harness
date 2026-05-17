from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.services.skills import write_skill_files_atomic


def test_write_skill_files_atomic_rolls_back_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text("original graph\n", encoding="utf-8")
    original_rename = os.rename
    rename_calls: list[tuple[Path, Path]] = []

    def fail_tmp_promotion(src: Path | str, dst: Path | str) -> None:
        source = Path(src)
        target = Path(dst)
        rename_calls.append((source, target))
        if source.name.startswith(".demo-skill.tmp-") and target == skill_dir:
            raise OSError("simulated promotion failure")
        original_rename(source, target)

    monkeypatch.setattr("app.services.skills.os.rename", fail_tmp_promotion)

    with pytest.raises(OSError, match="simulated promotion failure"):
        write_skill_files_atomic(
            skill_dir,
            {
                "GRAPH.md": "new graph\n",
                "io/inputs.json": "{}\n",
                "io/outputs.json": "{}\n",
                "phases/init/LOGIC.md": "# init\n",
            },
        )

    assert (skill_dir / "GRAPH.md").read_text(encoding="utf-8") == "original graph\n"
    assert not (skill_dir / "io").exists()
    assert any(
        source == skill_dir and target.name.startswith(".demo-skill.bak-")
        for source, target in rename_calls
    )
    assert any(
        source.name.startswith(".demo-skill.bak-") and target == skill_dir
        for source, target in rename_calls
    )
    assert list(tmp_path.glob(".demo-skill.tmp-*")) == []
    assert list(tmp_path.glob(".demo-skill.bak-*")) == []
