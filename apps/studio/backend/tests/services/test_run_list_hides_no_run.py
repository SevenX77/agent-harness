"""A run the store cannot read is a fault to report, not a run to forget.

``list_runs`` used to wrap each row's read in ``except Exception: continue``, so
a ``run_metadata.json`` it could not parse produced a listing that was simply
one run shorter — with nothing logged, nothing raised, and no way for a reader
to tell a run that never existed from a run whose record could not be read.

That is what made the compare-group flake so hard to see: the metadata store
briefly truncated the file while re-saving it (fixed at that layer, see
``test_metadata_local``), and this except quietly turned "caught mid-save" into
"there is no such run". A store that cannot be read is worth saying out loud.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.services.run_manager import run_manager
from app.services.skills import runs_dir_for
from fastapi import HTTPException

GOOD_RUN = "2026-08-09T15-00-00_aaaaaaaa"
UNREADABLE_RUN = "2026-08-09T15-01-00_bbbbbbbb"


def _seed_run(root: Path, run_id: str, body: str) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(body, encoding="utf-8")
    return run_dir


def _valid_body(run_id: str) -> str:
    return json.dumps(
        {
            "run_id": run_id,
            "kind": "run",
            "status": "success",
            "started_at": "2026-08-09T15:00:00",
            "metrics": None,
            "input_summary": None,
        }
    )


def test_an_unreadable_run_record_is_reported_not_skipped(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    _seed_run(runs_root, GOOD_RUN, _valid_body(GOOD_RUN))
    _seed_run(runs_root, UNREADABLE_RUN, "")

    with pytest.raises(HTTPException) as raised:
        run_manager.list_runs("text-segmentation")

    assert raised.value.status_code == 500
    detail = raised.value.detail
    assert detail["error_code"] == "RUN_METADATA_UNREADABLE"  # type: ignore[index]
    # Naming the file is the whole point: the previous behaviour left the
    # operator with a shorter list and no idea which run went missing.
    assert UNREADABLE_RUN in json.dumps(detail)


def test_a_readable_store_still_lists_every_run(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    _seed_run(runs_root, GOOD_RUN, _valid_body(GOOD_RUN))
    _seed_run(runs_root, UNREADABLE_RUN, _valid_body(UNREADABLE_RUN))

    listed = run_manager.list_runs("text-segmentation")

    assert {row.run_id for row in listed.runs} == {GOOD_RUN, UNREADABLE_RUN}
    assert listed.total == 2
