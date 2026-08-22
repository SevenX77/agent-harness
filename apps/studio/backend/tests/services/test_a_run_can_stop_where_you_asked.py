"""A breakpoint is a thing you set on a node, and a run that hits one says so.

Two halves, and they meet at the worker.

The first half is the breakpoint itself: which nodes this skill is meant to stop
before. It is a property of the skill's workspace, so it lives beside every
other run-time choice in ``.workspace/runtime_config.json`` and travels to the
worker in the same snapshot — which also means the run's snapshot records the
breakpoints that were actually in force for it.

The second half is the ending. A run that stopped is neither a run that finished
nor a run that failed, and the worker had only those two branches: it asked
``_result_success``, whose contract is "Absent -> treat as success". The engine's
human-in-the-loop path returns a result with no ``success`` key at all, so every
stop was filed as a finish — including today, before breakpoints existed.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import RunMetadata
from app.services import run_manager as run_manager_module
from app.services.breakpoints import (
    breakpoints_from_runtime_config,
    clear_breakpoint,
    read_breakpoints,
    set_breakpoint,
)
from app.services.run_manager import RunManager, RunRecord, _result_pause_point
from app.services.runtime_config import read_runtime_config

SKILL = "text-segmentation"
RUN_ID = "run-stopped-at-a-breakpoint"


# --------------------------------------------------------------------------
# What a result means
# --------------------------------------------------------------------------


def test_a_stopped_run_is_not_read_as_a_finished_one() -> None:
    """The shape that made every human-in-the-loop stop look like a success.

    The engine's interrupted path returns a plain dict with no ``success`` key,
    and the host's only question was ``success``, where absent means yes.
    """
    stopped = {
        "run_id": RUN_ID,
        "context": {},
        "paused_at": {"phase_name": "review", "reason": "awaiting_human"},
    }

    pause_point = _result_pause_point(stopped)

    assert pause_point is not None
    assert pause_point.node_id == "review"
    assert pause_point.reason == "awaiting_human"


def test_a_finished_run_names_no_stopping_point() -> None:
    assert _result_pause_point({"run_id": RUN_ID, "success": True, "context": {}}) is None


def test_a_breakpoint_stop_says_it_was_a_breakpoint() -> None:
    """Reason is carried, not inferred: continuing needs no answer from anyone,
    while a run waiting on a human does — and the caller cannot tell which from
    the mere fact that the run stopped."""
    stopped = {
        "success": False,
        "paused_at": {"phase_name": "summarize", "reason": "breakpoint"},
    }

    pause_point = _result_pause_point(stopped)

    assert pause_point is not None
    assert pause_point.reason == "breakpoint"


# --------------------------------------------------------------------------
# The ending the worker reports
# --------------------------------------------------------------------------


class _FinishedWorker:
    """A worker that ran to completion and sent its verdict before exiting."""

    exitcode = 0

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        del timeout


def _run_record(run_dir: Path, message: dict[str, Any]) -> RunRecord:
    run_dir.mkdir(parents=True, exist_ok=True)
    process_queue: queue.Queue[Any] = queue.Queue()
    process_queue.put(message)
    return RunRecord(
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="running",
            started_at="2026-08-21T00:00:00+00:00",
        ),
        skill_id=SKILL,
        run_dir=run_dir,
        process=_FinishedWorker(),
        process_queue=process_queue,
    )


def _manager_that_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    return manager


_PAUSED_MESSAGE = {
    "type": "status",
    "status": "paused",
    "metrics": {},
    "paused_at": {"node_id": "review", "reason": "breakpoint"},
}


def test_a_run_that_stopped_at_a_breakpoint_is_recorded_paused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    record = _run_record(tmp_path / "runs" / RUN_ID, _PAUSED_MESSAGE)

    asyncio.run(manager._drain_process_queue(record))

    assert record.metadata.status == "paused"


def test_a_paused_run_says_which_node_it_stopped_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Without the node there is nothing to show: "it stopped" cannot be drawn
    on a canvas, and the user set the breakpoint on one particular node."""
    manager = _manager_that_writes_nothing(monkeypatch)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    run_dir = tmp_path / "runs" / RUN_ID
    record = _run_record(run_dir, _PAUSED_MESSAGE)

    asyncio.run(manager._drain_process_queue(record))

    assert record.metadata.paused_at is not None
    assert record.metadata.paused_at.node_id == "review"
    stored = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert stored["paused_at"]["node_id"] == "review"


def test_a_paused_run_is_not_sealed_as_though_it_were_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sealing means "nothing more will be written to this run", which is false
    of a run that is waiting to be continued — and the seal is what auto-commit
    and the report hang off."""
    manager = _manager_that_writes_nothing(monkeypatch)
    reports: list[Path] = []
    monkeypatch.setattr(run_manager_module, "write_run_report", reports.append)
    record = _run_record(tmp_path / "runs" / RUN_ID, _PAUSED_MESSAGE)

    asyncio.run(manager._drain_process_queue(record))

    assert reports == []


def test_a_paused_run_tells_the_surfaces_it_paused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager_that_writes_nothing(monkeypatch)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)
    record = _run_record(tmp_path / "runs" / RUN_ID, _PAUSED_MESSAGE)

    asyncio.run(manager._drain_process_queue(record))

    assert [entry["outcome"] for entry in published] == ["paused"]


# --------------------------------------------------------------------------
# Where a breakpoint is kept
# --------------------------------------------------------------------------


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skill"
    (root / ".workspace").mkdir(parents=True)
    return root


def test_a_skill_with_no_breakpoints_names_none(skill_dir: Path) -> None:
    assert read_breakpoints(skill_dir) == []


def test_a_breakpoint_set_on_a_node_is_read_back(skill_dir: Path) -> None:
    result = set_breakpoint(skill_dir, "review")

    assert result.changed is True
    assert read_breakpoints(skill_dir) == ["review"]


def test_setting_the_same_breakpoint_twice_changes_nothing(skill_dir: Path) -> None:
    """A write that changed nothing must not announce a change: the surfaces
    revalidate on the announcement, and one that says nothing new is a refetch
    with no data change behind it."""
    set_breakpoint(skill_dir, "review")

    assert set_breakpoint(skill_dir, "review").changed is False


def test_clearing_a_breakpoint_removes_it(skill_dir: Path) -> None:
    set_breakpoint(skill_dir, "review")
    set_breakpoint(skill_dir, "collect")

    assert clear_breakpoint(skill_dir, "review").changed is True
    assert read_breakpoints(skill_dir) == ["collect"]


def test_clearing_a_breakpoint_that_was_never_set_changes_nothing(skill_dir: Path) -> None:
    assert clear_breakpoint(skill_dir, "review").changed is False


def test_breakpoints_survive_beside_the_rest_of_the_workspace(skill_dir: Path) -> None:
    """They share the file with input bindings and per-node LLM params, so a
    breakpoint write must not be a whole-file replacement."""
    set_breakpoint(skill_dir, "review")

    config = read_runtime_config(skill_dir)

    assert config["breakpoints"] == ["review"]
    assert config["llm"]["node_params"] == {"nodes": {}}


def test_the_worker_is_handed_the_breakpoints_the_run_was_started_with() -> None:
    """The engine is told "stop before these phases" — it never reads Studio's
    workspace file, so the translation happens on this side of the boundary."""
    config = {"breakpoints": ["review", "collect"], "llm": {}}

    assert breakpoints_from_runtime_config(config) == ["collect", "review"]


def test_a_workspace_with_no_breakpoints_asks_for_no_stop() -> None:
    assert breakpoints_from_runtime_config({"llm": {}}) == []
