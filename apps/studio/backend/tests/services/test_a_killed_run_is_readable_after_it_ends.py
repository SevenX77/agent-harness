"""A run whose worker is killed still ends, and still reads back.

Problem ledger P1 recorded this as a frontend hole — "no watchdog, no heartbeat
timeout, so the badge spins until the user navigates away" — and proposed
building a watchdog in the projection layer. Measuring it first showed the
premise was wrong twice over.

`_drain_process_queue` already notices the process is gone, derives the outcome
from its exit code, writes the terminal metadata and publishes the run gate the
frontend's `finalize-run` effect listens for. A watchdog would have been a
second answer to a question already answered — and the worse answer, since the
frontend cannot see a worker die and would have to guess it from silence, which
a legitimately long phase also looks like.

What stranded the badge was the step AFTER that. The gate is a promise: this run
is finished, go read it. The frontend kept the promise and asked for the run;
the artifact store answered 409 `artifact.run_not_sealed`, the detail never
arrived, and the verdict stayed `running` for the rest of the session. Sealing
lived only inside `_persist_run_artifacts`, which runs IN the worker — the one
piece of code a killed worker cannot run. The finalizer already documented the
opposite as fact: "whoever sees it flip may immediately read the sealed run
dir".

So the seal moved to where the knowledge is. Sealing means "nothing more will be
written to this run", and only the parent can know a worker is never coming
back, so the parent is the only party that can say it truthfully — for every way
a run can end, not just the graceful one. `_finalize_terminal_run`, the single
place a run goes terminal, is where it is said.
"""

from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path
from typing import Any

import pytest
from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
from app.models.runs import RunMetadata
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager, RunRecord
from app.services.skills import runs_dir_for

SKILL = "text-segmentation"
RUN_ID = "run-killed"


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
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunRecord(
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="running",
            started_at="2026-08-20T00:00:00+00:00",
        ),
        skill_id=SKILL,
        run_dir=run_dir,
        process=_KilledWorker(),
        process_queue=queue.Queue(),
    )


def _manager_that_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    """A RunManager with only its persistence stubbed out.

    The drain loop and the finalize path themselves stay real — they are the
    subject. The storage backend, the metadata store and report rendering are
    replaced because they need a whole skill workspace on disk to say anything,
    and none of them is what decides whether a killed run reaches a terminal
    state. The RUN DIR is left alone: it is where the seal lands.
    """

    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    return manager


def _drained_killed_run(
    monkeypatch: pytest.MonkeyPatch, run_dir: Path
) -> tuple[RunManager, RunRecord]:
    manager = _manager_that_writes_nothing(monkeypatch)
    record = _run_record(run_dir)
    asyncio.run(manager._drain_process_queue(record))
    return manager, record


def test_a_killed_worker_leaves_the_run_failed_not_running(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, record = _drained_killed_run(monkeypatch, tmp_path / "runs" / RUN_ID)

    # No `status` message ever arrived — the worker died before sending one. The
    # exit code is the only thing left that describes the ending, and it has to
    # be enough, because nothing else is coming.
    assert record.metadata.status == "failed"


def test_a_killed_run_announces_its_own_ending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)
    record = _run_record(tmp_path / "runs" / RUN_ID)

    asyncio.run(manager._drain_process_queue(record))

    # Sealing the record privately would not converge anything: the frontend is
    # holding a projection built from events, and a run that dies without
    # emitting `run_ended` produces no event to change its mind. The gate is the
    # message that reaches it, and it has to name the run it is about.
    assert len(published) == 1
    assert published[0]["gate"] == "run"
    assert published[0]["outcome"] == "fail"
    assert published[0]["run_id"] == RUN_ID
    assert published[0]["skill_id"] == SKILL


def test_the_stream_is_closed_so_no_reader_waits_on_a_dead_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    record = _run_record(tmp_path / "runs" / RUN_ID)
    subscriber: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    record.subscribers.append(subscriber)

    asyncio.run(manager._drain_process_queue(record))

    # The sentinel is how a reader learns there will be no more frames. A
    # subscriber left hanging on a queue that will never fill again is the same
    # spinning-forever symptom, one layer down.
    assert record.ws_queue.get_nowait() is None
    assert subscriber.get_nowait() is None
    assert record.subscribers == []


def test_a_terminal_run_is_sealed_by_the_one_who_declares_it_terminal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate says "go read it", so by then it has to BE readable.

    The worker seals what it wrote, and a killed worker writes nothing — so the
    seal cannot be the worker's to give. The parent is the only party that knows
    no further object is coming.
    """
    run_dir = tmp_path / "runs" / RUN_ID
    _drained_killed_run(monkeypatch, run_dir)

    assert (run_dir / "sealed").exists()


def test_a_killed_run_keeps_the_trace_its_worker_got_as_far_as_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sealing over a live trace file would trade one lie for another.

    The worker streams `trace.jsonl` to the run dir as it goes, and only commits
    it to the store at the end. Sealing without that commit would leave the
    events sitting on disk and permanently outside the run — the detail would
    report "nothing happened" about a run that visibly did something.
    """
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "trace.jsonl").write_text(
        json.dumps({"event_type": "phase_started", "phase_id": "first"}) + "\n",
        encoding="utf-8",
    )

    _drained_killed_run(monkeypatch, run_dir)

    store = LocalRunArtifactStore(root=tmp_path)
    assert [ref.path for ref in store.list_run_objects(RUN_ID)] == ["trace.jsonl"]


def test_a_killed_runs_detail_reads_back_the_failure(
    monkeypatch: pytest.MonkeyPatch, studio_roots: tuple[Path, Path]
) -> None:
    """The end of the chain the badge actually depends on.

    A run killed before it produced anything has no final state and no events.
    Those are facts about the run, and `RunDetail` can state both — a null
    context and an empty list. Refusing to describe the run at all is the one
    answer that leaves the reader with nothing, which is what kept the verdict
    on `running`.
    """
    skills_dir, _ = studio_roots
    run_dir = runs_dir_for(skills_dir / SKILL) / RUN_ID
    manager, _ = _drained_killed_run(monkeypatch, run_dir)

    detail = manager.get_run_detail(SKILL, RUN_ID)

    assert detail.metadata.status == "failed"
    assert detail.final_context is None
    assert detail.events == []
    assert detail.artifacts == []
