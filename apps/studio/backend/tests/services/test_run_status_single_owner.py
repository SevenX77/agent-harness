"""A finished run must stop reporting `running`.

`get_run_detail` answers from the in-memory `RunRecord`, and the record used to
receive its terminal metadata as the very last statement of
`_finalize_terminal_run` — after two storage awaits. When one of those awaits
fails, the assignment is skipped and the record says `running` forever, so an
MCP client polling `get_run_detail` never learns that a sealed, successful run
has finished (observed 2026-08-03 on exp-b-round3 run
2026-08-03T07-01-08_ff0be8c9: `status: running` in the same response whose
`event_type_counts` already contained `run_ended: 1`).

The record stays the status owner on purpose. The run's `run_metadata.json`
goes terminal *before* `latest/` is synced, so reading status from disk would
announce the run as finished while finalization is still copying files.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.conftest import register_skill_index_entry


def _register_demo_skill(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, skill_dir: Path) -> None:
    from app.core import config

    monkeypatch.setattr(config, "SKILL_INDEX_PATH", tmp_path / "global-config" / "skill_index.json")
    register_skill_index_entry("demo.skill", skill_dir)


def _demo_skill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _register_demo_skill(monkeypatch, tmp_path, skill_dir)
    return skill_dir


def _record_for(run_dir: Path, status: str) -> object:
    from app.models.runs import RunMetadata
    from app.services.run_manager import RunRecord

    return RunRecord(
        metadata=RunMetadata(run_id=run_dir.name, status=status, started_at="2026-08-03T07:01:08Z"),
        skill_id="demo.skill",
        run_dir=run_dir,
        process=None,
        process_queue=None,
        auto_commit=False,
    )


def test_finalize_refreshes_the_record_even_when_a_storage_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.run_manager import RunManager

    skill_dir = _demo_skill_dir(tmp_path, monkeypatch)
    run_dir = skill_dir / ".workspace" / "runs" / "run-store-down"
    run_dir.mkdir(parents=True)

    manager = RunManager()
    record = _record_for(run_dir, "running")
    terminal = record.metadata.model_copy(update={"status": "success"})  # type: ignore[attr-defined]

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("run artifact storage unavailable")

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", _explode)

    with pytest.raises(RuntimeError):
        asyncio.run(manager._finalize_terminal_run(record, terminal))  # type: ignore[arg-type]

    assert record.metadata.status == "success"  # type: ignore[attr-defined]


def test_finalize_refreshes_the_record_when_the_metadata_store_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.run_manager import RunManager

    skill_dir = _demo_skill_dir(tmp_path, monkeypatch)
    run_dir = skill_dir / ".workspace" / "runs" / "run-late-store-down"
    run_dir.mkdir(parents=True)

    manager = RunManager()
    record = _record_for(run_dir, "running")
    terminal = record.metadata.model_copy(update={"status": "failed"})  # type: ignore[attr-defined]

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("metadata store unavailable")

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", _noop)
    monkeypatch.setattr(manager, "_save_run_metadata", _explode)

    with pytest.raises(RuntimeError):
        asyncio.run(manager._finalize_terminal_run(record, terminal))  # type: ignore[arg-type]

    assert record.metadata.status == "failed"  # type: ignore[attr-defined]
    assert (run_dir / "run_metadata.json").exists()


def test_run_detail_reports_the_terminal_status_after_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The MCP-facing projection must agree with the finished run."""
    from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore
    from app.services.run_manager import RunManager

    skill_dir = _demo_skill_dir(tmp_path, monkeypatch)
    run_dir = skill_dir / ".workspace" / "runs" / "run-sealed"
    run_dir.mkdir(parents=True)
    store = LocalRunArtifactStore(root=skill_dir / ".workspace")
    store.begin_run("run-sealed", metadata={"artifact_id": "demo.skill"})
    store.put_batch("run-sealed", {"final_state.json": b"{}", "trace.jsonl": b""})
    store.seal_run("run-sealed")

    manager = RunManager()
    record = _record_for(run_dir, "running")
    manager._runs["run-sealed"] = record  # type: ignore[assignment]

    async def _explode(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("run artifact storage unavailable")

    monkeypatch.setattr(manager, "_copy_final_state_to_storage", _explode)
    terminal = record.metadata.model_copy(update={"status": "success"})  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        asyncio.run(manager._finalize_terminal_run(record, terminal))  # type: ignore[arg-type]

    detail = manager.get_run_detail("demo.skill", "run-sealed")

    assert detail.metadata.status == "success"
