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


def test_every_spawn_states_whether_its_run_archives_the_skill() -> None:
    """``auto_commit`` has no default, so no spawn can inherit one by accident.

    A run that succeeds may commit the skill directory. Whether THIS run should
    is a property of what the run is — a real run, a predict, a compare
    candidate — and a default silently answers it for whoever forgets to.
    """
    field = next(f for f in dataclasses.fields(RunRecord) if f.name == "auto_commit")

    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING
    with pytest.raises(TypeError):
        RunRecord(  # type: ignore[call-arg]
            metadata=None,
            skill_id="s",
            run_dir=Path("."),
            process=None,
            process_queue=None,
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
