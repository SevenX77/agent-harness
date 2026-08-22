"""Three habits a run record must not have.

Each of these was found while fixing the compare-group flake and left alone so
that fix stayed one change. They are unrelated to each other except in origin,
and each one is a rule this codebase already states, applied where it was not.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path

import pytest
from app.core.adapters.atomic_file import write_text_atomically
from app.models.runs import RunMetadata
from app.services.run_manager import RunRecord
from app.services.skills import latest_run_metadata, runs_dir_for


def test_a_published_document_has_the_same_bytes_on_every_platform(tmp_path: Path) -> None:
    """UTF-8 + LF, per docs/development/CROSS_PLATFORM.md.

    Text mode translates line endings to the host's by default, so the same
    document published on Windows and on Linux would differ byte for byte —
    which turns every diff, hash and content comparison into a platform quiz.
    """
    path = tmp_path / "run_metadata.json"

    write_text_atomically(path, '{\n  "run_id": "r1"\n}\n')

    assert b"\r" not in path.read_bytes()


def test_whether_a_run_archives_the_skill_is_written_down_with_the_run() -> None:
    """And it defaults to the side that cannot damage anything.

    A run that succeeds may commit the skill directory. Whether THIS run should
    is a property of what the run is — a real run, a predict, a compare
    candidate — so it travels WITH the run rather than with the sidecar that
    spawned it: a sidecar taking a paused run over has only the run's own
    directory to read, and would otherwise have to guess.

    The default is "no". A side experiment that wrongly commits hands itself
    whatever the user changed while it ran; an ordinary run that wrongly does
    not just leaves its snapshot unmade. `start_run` is the one spawn that says
    yes (proved end to end by `test_successful_run_triggers_auto_commit`).
    """
    unstated = RunMetadata(run_id="r1", status="running", started_at="2026-08-22T00:00:00+00:00")

    assert unstated.auto_commit is False
    assert not any(field.name == "auto_commit" for field in dataclasses.fields(RunRecord)), (
        "the record must not hold a second copy of a fact its metadata already states"
    )


def test_a_run_record_it_cannot_read_is_named_not_silently_skipped(
    studio_roots: tuple[Path, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The skill list survives a damaged record, but it says which one.

    Blanking the whole skill list over one bad file would be the worse failure
    — that is why this one does not raise the way the run listing does. Doing it
    without a word, though, makes "latest run" quietly wrong: the screen shows
    an older run and nothing anywhere says a newer one was skipped.
    """
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    older = runs_root / "2026-08-09T10-00-00_aaaaaaaa"
    newer = runs_root / "2026-08-09T11-00-00_bbbbbbbb"
    for run_dir in (older, newer):
        run_dir.mkdir(parents=True)
    (older / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": older.name,
                "kind": "run",
                "status": "success",
                "started_at": "2026-08-09T10:00:00",
            }
        ),
        encoding="utf-8",
    )
    (newer / "run_metadata.json").write_text("{ truncated", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="app.services.skills"):
        latest = latest_run_metadata("text-segmentation")

    assert latest is not None
    assert latest.run_id == older.name
    assert newer.name in caplog.text
