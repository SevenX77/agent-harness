"""A failed run must keep the reason it failed.

The worker already knows why a run died — it puts the engine's error payload on
the status message (`run_manager._run_worker`). But `RunMetadata` had no field
to hold it and the drain copied only `status` + `metrics`, so the reason was
dropped on the floor: `run_metadata.json` and every API reader saw
`status: failed` with nothing else. Observed 2026-08-08 on a model-compare
side-run that died in 0.28s with `resource.no_available_route` — a diagnosis
that existed in the worker and reached no one.
"""

from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path

import pytest

from tests.conftest import register_skill_index_entry


class _FinishedProcess:
    """Stands in for the worker process after it has exited."""

    exitcode = 1

    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        return None


def _record_with(run_dir: Path, message: dict[str, object]) -> object:
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunRecord

    process_queue: queue.Queue[object] = queue.Queue()
    process_queue.put(message)
    return RunRecord(
        metadata=RunMetadata(run_id=run_dir.name, status="running", started_at="2026-08-08T09:47:48Z"),
        skill_id="demo.skill",
        run_dir=run_dir,
        process=_FinishedProcess(),
        process_queue=process_queue,
        auto_commit=False,
    )


def _demo_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from app.core import config
    from app.core.backends import clear_backend_caches

    skill_dir = tmp_path / "skills" / "demo"
    run_dir = skill_dir / ".workspace" / "runs" / "run-failed"
    run_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    global_config_dir = tmp_path / "global-config"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", global_config_dir)
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", global_config_dir / "skill_index.json")
    register_skill_index_entry("demo.skill", skill_dir)
    clear_backend_caches()
    return run_dir


def test_a_failed_run_reports_why_it_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.run_manager import RunManager

    run_dir = _demo_run_dir(tmp_path, monkeypatch)
    record = _record_with(
        run_dir,
        {
            "type": "status",
            "status": "failed",
            "metrics": {"wall_time_sec": 0.282},
            "error": {
                "code": "llm.provider_invoke_failed",
                "message": "resource.no_available_route - {'role': 'analyst'}",
                "details": {"role": "analyst"},
            },
        },
    )

    asyncio.run(RunManager()._drain_process_queue(record))  # type: ignore[attr-defined]

    error = record.metadata.error  # type: ignore[attr-defined]
    assert error is not None
    assert error.code == "llm.provider_invoke_failed"
    assert "no_available_route" in error.message

    on_disk = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert on_disk["error"]["code"] == "llm.provider_invoke_failed"


def test_a_successful_run_carries_no_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.run_manager import RunManager

    run_dir = _demo_run_dir(tmp_path, monkeypatch)
    record = _record_with(
        run_dir,
        {"type": "status", "status": "success", "metrics": {"wall_time_sec": 1.0}},
    )

    asyncio.run(RunManager()._drain_process_queue(record))  # type: ignore[attr-defined]

    assert record.metadata.error is None  # type: ignore[attr-defined]
    assert "error" not in json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))


def test_finishing_a_run_leaves_a_report_beside_its_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every finished run gets its report (run-execution mvp1-alignment F6)."""
    from app.services.run_manager import RunManager

    run_dir = _demo_run_dir(tmp_path, monkeypatch)
    record = _record_with(
        run_dir,
        {"type": "status", "status": "success", "metrics": {"wall_time_sec": 1.0}},
    )

    asyncio.run(RunManager()._drain_process_queue(record))  # type: ignore[attr-defined]

    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Run report")
    assert run_dir.name in report
