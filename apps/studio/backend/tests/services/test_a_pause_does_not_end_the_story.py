"""A run that stopped is not over, so its event stream is not over either.

Found by walking the whole breakpoint round on the real machine (problem ledger
C1 ③). Set two breakpoints, run, stop before the first — all correct. Press
Resume: on disk the run advanced a phase and stopped at the second breakpoint,
exactly as designed, while the canvas kept showing the first stop.

The sink added for the resumed segment's events was writing into a closed pipe.
When the worker exits at a pause, the drain loop ends and closes the run's
stream — the same `None` sentinel and the same `subscribers.clear()` a finished
run gets. But continuing the run writes more of the SAME run's story, to the
same subscribers, under the same run id. Ending the stream at a stop is the
same category error as filing a stop as a finish, one layer down: the stream
belongs to the run, and the run has not ended.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import asyncio
import queue
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import RunMetadata, RunPausePoint
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager, RunRecord

SKILL = "text-segmentation"
RUN_ID = "run-stopped"


class _WorkerThatExited:
    """A paused run's worker is gone: it reported the stop and returned."""

    exitcode = 0

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        del timeout


def _manager(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    return manager


def _record(run_dir: Path, worker_says: dict[str, Any]) -> RunRecord:
    run_dir.mkdir(parents=True, exist_ok=True)
    process_queue: queue.Queue[Any] = queue.Queue()
    process_queue.put(worker_says)
    return RunRecord(
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="running",
            started_at="2026-08-22T00:00:00+00:00",
        ),
        skill_id=SKILL,
        run_dir=run_dir,
        process=_WorkerThatExited(),
        process_queue=process_queue,
    )


async def _drain(manager: RunManager, record: RunRecord) -> list[Any]:
    manager._runs[RUN_ID] = record
    await manager._drain_process_queue(record)
    delivered: list[Any] = []
    while not record.ws_queue.empty():
        delivered.append(record.ws_queue.get_nowait())
    return delivered


@pytest.mark.anyio
async def test_a_run_that_stopped_keeps_its_stream_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(monkeypatch)
    watcher: asyncio.Queue[Any] = asyncio.Queue()
    record = _record(
        tmp_path / "runs" / RUN_ID,
        {"type": "status", "status": "paused", "paused_at": {"node_id": "beta", "reason": "breakpoint"}},
    )
    record.subscribers.append(watcher)

    delivered = await _drain(manager, record)

    assert None not in delivered, "the stop closed the run's stream"
    assert record.subscribers == [watcher], "the stop dropped whoever was watching"


@pytest.mark.anyio
async def test_a_stopped_runs_next_events_reach_the_same_watchers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The point of keeping it open: press Resume and the canvas moves."""
    manager = _manager(monkeypatch)
    watcher: asyncio.Queue[Any] = asyncio.Queue()
    record = _record(
        tmp_path / "runs" / RUN_ID,
        {"type": "status", "status": "paused", "paused_at": {"node_id": "beta", "reason": "breakpoint"}},
    )
    record.subscribers.append(watcher)
    await _drain(manager, record)

    observe = manager.observe_resumed_run(RUN_ID, skill_id=SKILL)
    assert observe is not None
    observe({"event_type": "phase_start", "phase_name": "beta", "run_id": RUN_ID})

    delivered = watcher.get_nowait()
    assert delivered["payload"]["event_type"] == "phase_start"


@pytest.mark.anyio
async def test_a_run_that_ended_still_closes_its_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other half of the rule: an ending still ends the stream, or every
    reader waits forever for a run that will never write another word."""
    manager = _manager(monkeypatch)
    watcher: asyncio.Queue[Any] = asyncio.Queue()
    record = _record(tmp_path / "runs" / RUN_ID, {"type": "status", "status": "success"})
    record.subscribers.append(watcher)

    delivered = await _drain(manager, record)

    assert delivered[-1] is None
    assert record.subscribers == []
    assert watcher.get_nowait() is None


@pytest.mark.anyio
async def test_a_run_whose_worker_died_without_a_word_closes_its_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A killed worker reports nothing at all, and that is an ending too — the
    stream must not be held open by a run nobody can continue."""
    manager = _manager(monkeypatch)
    record = _record(tmp_path / "runs" / RUN_ID, {"type": "ignored"})
    record.metadata = record.metadata.model_copy(update={"status": "running"})

    delivered = await _drain(manager, record)

    assert delivered[-1] is None


@pytest.mark.anyio
async def test_a_resumed_run_that_stops_again_keeps_the_stream_open(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A second stop is a stop like the first: there can be a third segment."""
    from app.models.runs import ResumeReport, ResumeReq

    manager = _manager(monkeypatch)
    watcher: asyncio.Queue[Any] = asyncio.Queue()
    record = _record(
        tmp_path / "runs" / RUN_ID,
        {"type": "status", "status": "paused", "paused_at": {"node_id": "beta", "reason": "breakpoint"}},
    )
    record.subscribers.append(watcher)
    await _drain(manager, record)
    while not watcher.empty():
        watcher.get_nowait()

    await manager.record_resume_result(
        skill_id=SKILL,
        run_id=RUN_ID,
        request=ResumeReq(),
        report=ResumeReport(
            status="paused",
            paused_at=RunPausePoint(node_id="gamma", reason="breakpoint"),
        ),
    )

    delivered = []
    while not watcher.empty():
        delivered.append(watcher.get_nowait())
    assert None not in delivered
    assert record.subscribers == [watcher]
