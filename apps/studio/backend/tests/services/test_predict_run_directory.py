"""Predict keeps its own directory; the run list still shows one history.

Decision `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D13:
"predict 与 run 分目录存放 ... 磁盘分开,但 UI 仍是一个列表 ... 因此 `list_runs`
必须同时扫描两个目录。"
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.adapters.run_layout import PREDICTS_DIRNAME, RUNS_DIRNAME
from app.services.run_ids import is_predict_run_id, new_predict_run_id, new_run_id
from app.services.run_manager import run_manager
from app.services.skills import predicts_dir_for, run_root_for, runs_dir_for

RUN_ID = "2026-08-09T13-40-42_aaaaaaaa"
PREDICT_ID = "predict-2026-08-09T13-41-00_bbbbbbbb"


def _seed_run(skill_dir: Path, root: Path, run_id: str, kind: str) -> None:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "kind": kind,
                "status": "success",
                "started_at": "2026-08-09T13:40:42",
                "metrics": None,
                "input_summary": None,
            }
        ),
        encoding="utf-8",
    )


def test_a_run_id_says_which_root_it_belongs_to() -> None:
    """Studio mints both shapes, so Studio can read the kind back off the id."""
    assert is_predict_run_id(new_predict_run_id())
    assert not is_predict_run_id(new_run_id())


def test_the_two_kinds_resolve_to_different_roots(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo"

    assert run_root_for(skill_dir, RUN_ID) == skill_dir / ".workspace" / RUNS_DIRNAME
    assert run_root_for(skill_dir, PREDICT_ID) == skill_dir / ".workspace" / PREDICTS_DIRNAME


def test_list_runs_reads_both_roots_into_one_history(studio_roots: tuple[Path, Path]) -> None:
    """Split on disk, single list on screen — so listing has to visit both."""
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    _seed_run(skill_dir, runs_dir_for(skill_dir), RUN_ID, "run")
    _seed_run(skill_dir, predicts_dir_for(skill_dir), PREDICT_ID, "predict")

    listed = run_manager.list_runs("text-segmentation")

    assert {entry.run_id for entry in listed.runs} == {RUN_ID, PREDICT_ID}
    assert listed.total == 2


def test_a_predict_leaves_nothing_in_the_runs_root(studio_roots: tuple[Path, Path]) -> None:
    """The point of the split: clearing rehearsals can never touch a run."""
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    _seed_run(skill_dir, predicts_dir_for(skill_dir), PREDICT_ID, "predict")

    assert not runs_dir_for(skill_dir).exists()
