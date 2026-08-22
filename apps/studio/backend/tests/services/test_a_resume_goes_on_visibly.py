"""Continuing a stopped run has to be visible, and has to keep stopping.

Found by walking a breakpoint through the real window (problem ledger C1 ③).
Set a breakpoint, run, watch it stop before the phase — all correct. Then press
Resume: on disk the run finished, and the canvas went on showing the moment it
stopped, forever. Four separate holes, all on the resume path, all the same
shape as the ones the first-run path had already been fixed for:

1. The resumed segment's events reached the trace file and nobody else. The
   endpoint runs the engine in-process with no subscriber, so the live view —
   which is built from events — had nothing to build from.
2. Nothing announced the ending. `_seal_terminal_run` publishes the run gate the
   surfaces listen for; `record_resume_result` published nothing at all.
3. The engine's third ending was collapsed back to two on the way out
   (`"success" if res.success else "failed"`), so a resume that stopped at the
   NEXT breakpoint was recorded as a failure.
4. The resume never passed the breakpoints on, so the continued run was compiled
   without them and would run straight through every remaining one.

And a fifth, found by CI on the fix for the fourth: asking for the marks by
resolving the LIVE skill directory made the endpoint answer 404 SKILL_NOT_FOUND
for every skill this Studio does not hold open — swallowing the runtime-state
errors the endpoint exists to report. A run resumes from its own artifact; the
skill directory is consulted, not required.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import ResumeReq, RunMetadata, RunPausePoint
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager, RunRecord
from fastapi.testclient import TestClient

SKILL = "text-segmentation"
RUN_ID = "run-resumed"


class _NoWorker:
    """A resume has no worker process: the engine runs in the request itself."""

    exitcode = 0

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        del timeout


def _record(run_dir: Path) -> RunRecord:
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunRecord(
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="paused",
            started_at="2026-08-22T00:00:00+00:00",
            paused_at=RunPausePoint(node_id="beta", reason="breakpoint"),
        ),
        skill_id=SKILL,
        run_dir=run_dir,
        process=_NoWorker(),
        process_queue=queue.Queue(),
        auto_commit=False,
    )


def _manager(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    return manager


def _finished(**overrides: Any) -> RunMetadata:
    return RunMetadata(
        run_id=RUN_ID,
        status="success",
        started_at="2026-08-22T00:00:00+00:00",
        **overrides,
    )


@pytest.mark.anyio
async def test_a_resumed_run_announces_that_it_ended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate is the message that reaches the surfaces. Without it the canvas
    holds the picture it had when the run stopped — which is now a lie."""
    manager = _manager(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)
    record = _record(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    await manager.record_resume_result(
        skill_id=SKILL, run_id=RUN_ID, request=ResumeReq(), metadata=_finished()
    )

    assert [entry["outcome"] for entry in published] == ["pass"]
    assert published[0]["run_id"] == RUN_ID


@pytest.mark.anyio
async def test_a_resume_that_stops_again_says_so_rather_than_saying_it_passed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(monkeypatch)
    published: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        published.append(kwargs)

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", capture)
    record = _record(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    stopped_again = RunMetadata(
        run_id=RUN_ID,
        status="paused",
        started_at="2026-08-22T00:00:00+00:00",
        paused_at=RunPausePoint(node_id="gamma", reason="breakpoint"),
    )
    result = await manager.record_resume_result(
        skill_id=SKILL, run_id=RUN_ID, request=ResumeReq(), metadata=stopped_again
    )

    assert result.paused_at is not None
    assert result.paused_at.node_id == "gamma"
    assert [entry["outcome"] for entry in published] == ["paused"]


@pytest.mark.anyio
async def test_a_resumed_runs_events_reach_whoever_is_watching_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The live view is built from events; a segment that emits none is
    invisible no matter how correctly it ran."""
    manager = _manager(monkeypatch)

    async def noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    record = _record(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    subscriber = manager.observe_resumed_run(RUN_ID)
    assert subscriber is not None
    subscriber({"event_type": "phase_start", "phase_name": "beta", "run_id": RUN_ID})
    subscriber({"event_type": "phase_end", "phase_name": "beta", "run_id": RUN_ID})

    await manager.record_resume_result(
        skill_id=SKILL, run_id=RUN_ID, request=ResumeReq(), metadata=_finished()
    )

    delivered = []
    while not record.ws_queue.empty():
        item = record.ws_queue.get_nowait()
        if item is None:
            break
        delivered.append(item)
    types = [entry.get("event_type") or entry.get("payload", {}).get("event_type") for entry in delivered]
    assert "phase_start" in types
    assert "phase_end" in types


def test_a_run_with_no_record_here_has_nobody_to_show_events_to() -> None:
    """Another sidecar's paused run can still be resumed; there is simply no
    live watcher on this side, and inventing a queue for one would be a second
    place the run's events live."""
    assert RunManager().observe_resumed_run("run-nobody-here") is None


@pytest.mark.anyio
async def test_a_resumed_run_that_stopped_again_is_not_sealed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(monkeypatch)
    reports: list[Path] = []
    monkeypatch.setattr(run_manager_module, "write_run_report", reports.append)

    async def noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    record = _record(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    await manager.record_resume_result(
        skill_id=SKILL,
        run_id=RUN_ID,
        request=ResumeReq(),
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="paused",
            started_at="2026-08-22T00:00:00+00:00",
            paused_at=RunPausePoint(node_id="gamma", reason="breakpoint"),
        ),
    )

    assert reports == []


def _resume_result(*, success: bool, paused_at: dict[str, str] | None) -> Any:
    class _Result:
        pass

    result = _Result()
    result.success = success
    result.paused_at = paused_at
    result.metrics = {}
    result.started_at = None
    return result


def test_the_third_ending_survives_the_trip_out_of_the_engine() -> None:
    """`"success" if res.success else "failed"` is the same two-valued question
    the worker used to ask, and it turns a run that stopped at the next
    breakpoint into a failure."""
    from app.core.adapters.engine import resume_outcome

    stopped = resume_outcome(
        _resume_result(success=False, paused_at={"phase_name": "gamma", "reason": "breakpoint"})
    )

    assert stopped.status == "paused"
    assert stopped.paused_at == {"node_id": "gamma", "reason": "breakpoint"}


def test_a_resume_that_ran_to_the_end_is_a_success() -> None:
    from app.core.adapters.engine import resume_outcome

    finished = resume_outcome(_resume_result(success=True, paused_at=None))

    assert finished.status == "success"
    assert finished.paused_at is None


def test_a_resume_that_failed_is_still_a_failure() -> None:
    from app.core.adapters.engine import resume_outcome

    failed = resume_outcome(_resume_result(success=False, paused_at=None))

    assert failed.status == "failed"
    assert failed.paused_at is None


def test_marks_on_a_skill_this_studio_does_not_hold_are_no_marks() -> None:
    """Asking has to have an answer, because a resume can outlive the opening.

    The marks live in the skill's workspace, so reading them means naming a
    directory — and this Studio may hold no directory under that id: the skill
    was closed, or the run is being resumed in a sidecar that never opened it.
    That is not a failure to answer. Nobody could have set a mark on a skill
    nobody has open, so "none" is the whole truth.
    """
    from app.services.breakpoints import breakpoints_for_skill

    assert breakpoints_for_skill("a-skill-nobody-here-has-open") == []


def test_a_resume_reports_the_runtime_state_error_even_with_no_skill_dir_to_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression CI caught: reading the marks must not be able to fail the
    resume. Resolving the live skill directory raises SKILL_NOT_FOUND, and that
    404 landed on top of a `state.lease_conflict` the caller has to see."""
    import app.core.adapters.transport_factory as transport_factory
    from app.core.adapters.http_transport import StudioAdapterError
    from app.main import create_app

    conflict = {"run_id": "run-1", "active_owner": "worker-a"}

    class _Adapter:
        def resume(self, _payload: dict[str, Any]) -> dict[str, Any]:
            raise StudioAdapterError("state.lease_conflict", conflict)

    monkeypatch.setattr(transport_factory, "build_engine_adapter", lambda: _Adapter())

    with TestClient(create_app(), raise_server_exceptions=False) as api_client:
        api_client.headers["Authorization"] = "Bearer studio-test-token"
        response = api_client.post(
            "/api/skills/a-skill-nobody-here-has-open/runs/run-1/resume",
            json={"human_input": "continue"},
        )

    assert response.status_code == 409
    assert response.json()["error_code"] == "state.lease_conflict"
