"""A paused run outlives the sidecar that started it, and can be continued there.

Found while walking the breakpoint feature on the real machine (problem ledger
C1 ③): a run stopped at a breakpoint, the app was closed and reopened, Resume
was pressed. On disk the run advanced a phase and finished — correctly. On
screen nothing moved, and nothing moved until the app was reopened again.

An in-memory record dies with the process that held it. `stop_run` already
learned to end a run through its directory alone (C1 ④), because ending is a
write. Resuming is not: it PRODUCES — events while it runs, an ending to
announce — and a record is where a run's stream and its watchers live. Without
one, `observe_resumed_run` had nowhere to send the events and
`record_resume_result` published no gate.

So the sidecar that resumes a paused run takes it over, rebuilding the record
from the durable artifact — the same move a supervisor makes when it re-adopts
a service it did not launch, rather than starting a second one. Watching a
paused run does the same for the same reason: a paused run is going to write
again, so somebody has to be holding the pen.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import RunMetadata, RunPausePoint
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager

SKILL = "text-segmentation"
RUN_ID = "2026-08-22T00-00-00_abandoned-by-its-sidecar"


def _paused_run_on_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Path:
    """A run directory left behind by a sidecar that is gone."""
    run_dir = tmp_path / SKILL / ".workspace" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    metadata = RunMetadata(
        run_id=RUN_ID,
        status="paused",
        started_at="2026-08-22T00:00:00+00:00",
        paused_at=RunPausePoint(node_id="beta", reason="breakpoint"),
        **overrides,
    )
    (run_dir / "run_metadata.json").write_text(
        metadata.model_dump_json(exclude_none=True), encoding="utf-8"
    )
    # The skill is open here, which is how the run's directory is reachable at
    # all; the layout under it is the real one, so `run_root_for` finds the run.
    # Both forms of the lookup: taking a run over asks the non-raising one,
    # replaying a finished one still goes through the raising one.
    from app.services import skills as skills_module

    monkeypatch.setattr(
        run_manager_module, "opened_skill_dir", lambda _skill_id: tmp_path / SKILL
    )
    monkeypatch.setattr(skills_module, "resolve_skill_dir", lambda _skill_id: tmp_path / SKILL)
    return run_dir


def _manager(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    return manager


def test_a_resume_takes_over_a_run_this_sidecar_never_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _paused_run_on_disk(tmp_path, monkeypatch)
    manager = _manager(monkeypatch)

    observe = manager.observe_resumed_run(RUN_ID, skill_id=SKILL)

    assert observe is not None, "the resumed segment had nowhere to send its events"
    observe({"event_type": "phase_start", "phase_name": "beta", "run_id": RUN_ID})
    record = manager._runs[RUN_ID]
    assert record.events[-1].payload["event_type"] == "phase_start"


def test_a_taken_over_run_announces_its_ending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _paused_run_on_disk(tmp_path, monkeypatch)
    manager = _manager(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)
    manager.observe_resumed_run(RUN_ID, skill_id=SKILL)

    from app.models.runs import ResumeReq

    asyncio.run(
        manager.record_resume_result(
            skill_id=SKILL,
            run_id=RUN_ID,
            request=ResumeReq(),
            metadata=RunMetadata(
                run_id=RUN_ID, status="success", started_at="2026-08-22T00:00:00+00:00"
            ),
        )
    )

    assert [entry["outcome"] for entry in published] == ["pass"]


def test_a_run_that_ended_is_not_taken_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Nothing more will be written, so there is nothing to hold."""
    run_dir = _paused_run_on_disk(tmp_path, monkeypatch)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "status": "success",
                "started_at": "2026-08-22T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    manager = _manager(monkeypatch)

    assert manager.observe_resumed_run(RUN_ID, skill_id=SKILL) is None


def test_whether_a_run_archives_the_skill_survives_the_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """It is a property of what the run IS, so it is written down with the run.

    Held only in memory, a taken-over run had to be guessed at: archive a side
    experiment and it commits whatever the user changed while it ran; refuse to
    archive an ordinary run and its snapshot silently never appears.
    """
    _paused_run_on_disk(tmp_path, monkeypatch, auto_commit=True)
    manager = _manager(monkeypatch)

    manager.observe_resumed_run(RUN_ID, skill_id=SKILL)

    assert manager._runs[RUN_ID].metadata.auto_commit is True


def test_a_side_run_taken_over_still_does_not_archive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _paused_run_on_disk(tmp_path, monkeypatch, auto_commit=False)
    manager = _manager(monkeypatch)

    manager.observe_resumed_run(RUN_ID, skill_id=SKILL)

    assert manager._runs[RUN_ID].metadata.auto_commit is False


@pytest.mark.anyio
async def test_watching_a_paused_run_keeps_the_socket_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A paused run is going to write again; a watcher told "that's all" has to
    reconnect on a timer to find out, and misses everything until it does."""
    _paused_run_on_disk(tmp_path, monkeypatch)
    manager = _manager(monkeypatch)

    queue = await manager.stream_run(SKILL, RUN_ID)

    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    assert None not in drained, "the watcher was told the paused run was over"
    assert queue in manager._runs[RUN_ID].subscribers


@pytest.mark.anyio
async def test_watching_a_finished_run_still_ends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_dir = _paused_run_on_disk(tmp_path, monkeypatch)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {"run_id": RUN_ID, "status": "success", "started_at": "2026-08-22T00:00:00+00:00"}
        ),
        encoding="utf-8",
    )
    manager = _manager(monkeypatch)

    queue = await manager.stream_run(SKILL, RUN_ID)

    drained = []
    while not queue.empty():
        drained.append(queue.get_nowait())
    assert drained[-1] is None
    assert RUN_ID not in manager._runs
