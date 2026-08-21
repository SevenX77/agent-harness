"""A run whose worker is killed still reaches a terminal state, and says so.

Problem ledger P1 recorded this as a frontend hole — "no watchdog, no heartbeat
timeout, so the badge spins until the user navigates away" — and proposed
building a watchdog in the projection layer. Measuring it first showed the
premise was wrong: `_drain_process_queue` already notices the process is gone,
derives the outcome from its exit code, seals the metadata, and publishes the
run gate that the frontend's `finalize-run` effect listens for.

Nothing covered that path, which is how a diagnosis like P1's can drift away
from the code and stay plausible. These tests hold the two halves that a
convergent badge depends on: the run must go terminal, and someone must be
TOLD. A watchdog would have been a second answer to a question already
answered — and a wrong second answer, since the frontend cannot see a worker
die and would have had to guess.
"""

from __future__ import annotations

import asyncio
import queue
import tempfile
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import RunMetadata
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager, RunRecord


class _KilledWorker:
    """A worker that was killed: never alive, killed-by-signal exit, silent queue.

    137 is what `kill -9` and `taskkill /f` leave behind (128 + SIGKILL). The
    number does not matter to the code under test — anything non-zero is a
    failure — but using the real one keeps the fixture recognisable as the
    scenario the ledger row is about, rather than an abstract "process ended".
    """

    exitcode = 137

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        del timeout


def _run_record(run_dir: Path) -> RunRecord:
    return RunRecord(
        metadata=RunMetadata(
            run_id="run-killed",
            status="running",
            started_at="2026-08-20T00:00:00+00:00",
        ),
        skill_id="demo.skill",
        run_dir=run_dir,
        process=_KilledWorker(),
        process_queue=queue.Queue(),
        auto_commit=False,
    )


def _manager_that_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    """A RunManager with only its persistence stubbed out.

    The drain loop and the finalize path themselves stay real — they are the
    subject. Storage, metadata save and report rendering are replaced because
    they need a whole skill workspace on disk to say anything, and none of them
    is what decides whether a killed run reaches a terminal state.
    """

    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    return manager


def test_a_killed_worker_leaves_the_run_failed_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)

    with tempfile.TemporaryDirectory() as tmp:
        record = _run_record(Path(tmp))

        asyncio.run(manager._drain_process_queue(record))

        # No `status` message ever arrived — the worker died before sending one.
        # The exit code is the only thing left that describes the ending, and it
        # has to be enough, because nothing else is coming.
        assert record.metadata.status == "failed"


def test_a_killed_run_announces_its_own_ending(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)

    with tempfile.TemporaryDirectory() as tmp:
        record = _run_record(Path(tmp))

        asyncio.run(manager._drain_process_queue(record))

    # Sealing the record privately would not converge anything: the frontend is
    # holding a projection built from events, and a run that dies without
    # emitting `run_ended` produces no event to change its mind. The gate is the
    # message that reaches it, and it has to name the run it is about.
    assert len(published) == 1
    assert published[0]["gate"] == "run"
    assert published[0]["outcome"] == "fail"
    assert published[0]["run_id"] == "run-killed"
    assert published[0]["skill_id"] == "demo.skill"


def test_the_stream_is_closed_so_no_reader_waits_on_a_dead_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)

    async def noop_publish(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop_publish)

    with tempfile.TemporaryDirectory() as tmp:
        record = _run_record(Path(tmp))
        subscriber: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        record.subscribers.append(subscriber)

        asyncio.run(manager._drain_process_queue(record))

        # The sentinel is how a reader learns there will be no more frames. A
        # subscriber left hanging on a queue that will never fill again is the
        # same spinning-forever symptom, one layer down.
        assert record.ws_queue.get_nowait() is None
        assert subscriber.get_nowait() is None
        assert record.subscribers == []
