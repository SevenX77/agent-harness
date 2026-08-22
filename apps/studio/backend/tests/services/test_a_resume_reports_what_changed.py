"""A resume says what one segment did; it does not re-issue the run's record.

Found on the real machine (problem ledger C1 ③), reading a finished run's
`run_metadata.json` after two resumes: `auto_commit` was false on an ordinary
run that had asked for it, `input_summary` read "resumed" instead of what the
run was given, and `started_at` was the last resume's clock rather than the
run's.

All three are one defect. The endpoint built a whole new `RunMetadata` out of
the adapter's answer, so every field that answer did not mention reverted to
its default. It had been noticed once already and patched one field at a time —
`_preserve_resume_artifact_identity` restored three of them by hand — which is
a list that has to be extended every time the model grows, and was not.

A resumed segment knows three things: how it ended, what it spent, and where it
stopped. The run is the run.

Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest
from app.models.runs import ResumeReport, ResumeReq, RunMetadata, RunPausePoint, TokensMetrics
from app.services import run_manager as run_manager_module
from app.services.run_manager import RunManager, RunRecord

SKILL = "text-segmentation"
RUN_ID = "run-resumed-twice"


def _manager(monkeypatch: pytest.MonkeyPatch) -> RunManager:
    manager = RunManager()

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", noop)
    monkeypatch.setattr(manager, "_save_run_metadata", noop)
    monkeypatch.setattr(run_manager_module, "publish_skill_gate", noop)
    monkeypatch.setattr(run_manager_module, "write_run_report", lambda _dir: None)
    return manager


class _NoWorker:
    exitcode = 0

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        del timeout


def _ordinary_run(run_dir: Path) -> RunRecord:
    """A run started the ordinary way: it archives, it says what it was given."""
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunRecord(
        metadata=RunMetadata(
            run_id=RUN_ID,
            status="paused",
            started_at="2026-08-22T01:00:00+00:00",
            input_summary="topic=segmentation",
            auto_commit=True,
            artifact_ref={"artifact_id": "k1", "content_hash": "sha256:abc"},
            source_map_ref="map-1",
            execution_fingerprint="fp-1",
            paused_at=RunPausePoint(node_id="beta", reason="breakpoint"),
        ),
        skill_id=SKILL,
        run_dir=run_dir,
        process=_NoWorker(),
        process_queue=queue.Queue(),
    )


@pytest.mark.anyio
async def test_a_resume_keeps_everything_it_was_not_about(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(monkeypatch)
    record = _ordinary_run(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    finished = await manager.record_resume_result(
        skill_id=SKILL,
        run_id=RUN_ID,
        request=ResumeReq(),
        report=ResumeReport(status="success"),
    )

    assert finished.auto_commit is True, "an ordinary run stopped archiving because it was resumed"
    assert finished.input_summary == "topic=segmentation"
    assert finished.started_at.isoformat() == "2026-08-22T01:00:00+00:00"
    assert finished.artifact_ref == {"artifact_id": "k1", "content_hash": "sha256:abc"}
    assert finished.source_map_ref == "map-1"
    assert finished.execution_fingerprint == "fp-1"


@pytest.mark.anyio
async def test_a_resume_says_the_three_things_it_knows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(monkeypatch)
    record = _ordinary_run(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    stopped_again = await manager.record_resume_result(
        skill_id=SKILL,
        run_id=RUN_ID,
        request=ResumeReq(),
        report=ResumeReport(
            status="paused",
            metrics=TokensMetrics(input_tokens=40, output_tokens=59, total_tokens=99),
            paused_at=RunPausePoint(node_id="gamma", reason="breakpoint"),
        ),
    )

    assert stopped_again.status == "paused"
    assert stopped_again.metrics is not None
    assert stopped_again.metrics.total_tokens == 99
    assert stopped_again.paused_at is not None
    assert stopped_again.paused_at.node_id == "gamma"


@pytest.mark.anyio
async def test_a_resume_that_ran_to_the_end_leaves_no_stopping_point_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The run stopped before `beta` and then went past it; a record still
    naming that point would say a finished run is waiting somewhere."""
    manager = _manager(monkeypatch)
    record = _ordinary_run(tmp_path / "runs" / RUN_ID)
    manager._runs[RUN_ID] = record

    finished = await manager.record_resume_result(
        skill_id=SKILL, run_id=RUN_ID, request=ResumeReq(), report=ResumeReport(status="success")
    )

    assert finished.paused_at is None


@pytest.mark.anyio
async def test_a_resume_of_a_run_from_another_sidecar_updates_what_is_on_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No record here, but the run's own directory still holds its record —
    which is exactly what must be updated rather than replaced."""
    manager = _manager(monkeypatch)
    run_dir = tmp_path / SKILL / ".workspace" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        RunMetadata(
            run_id=RUN_ID,
            status="paused",
            started_at="2026-08-22T01:00:00+00:00",
            input_summary="topic=segmentation",
            auto_commit=True,
        ).model_dump_json(exclude_none=True),
        encoding="utf-8",
    )
    from app.services import skills as skills_module

    monkeypatch.setattr(run_manager_module, "opened_skill_dir", lambda _skill_id: tmp_path / SKILL)
    monkeypatch.setattr(skills_module, "resolve_skill_dir", lambda _skill_id: tmp_path / SKILL)

    finished = await manager.record_resume_result(
        skill_id=SKILL, run_id=RUN_ID, request=ResumeReq(), report=ResumeReport(status="success")
    )

    assert finished.auto_commit is True
    assert finished.input_summary == "topic=segmentation"
    assert finished.status == "success"


def test_the_adapter_reports_a_segment_not_a_run() -> None:
    """The dict crossing the adapter boundary carries the segment's answer only.

    `started_at` and a literal `input_summary: "resumed"` used to ride along and
    overwrite the run's own — the run started when it started, and it was given
    what it was given.
    """
    from app.core.adapters.engine import resume_result

    class _Result:
        success = True
        paused_at = None

    payload = resume_result(run_id=RUN_ID, res=_Result(), metrics={"total_tokens": 7})

    assert set(payload) == {"run_id", "status", "metrics"}
    assert payload["status"] == "success"
