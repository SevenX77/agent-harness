"""N6/F1: a successful run in a non-git workspace is a benign 'no_git' boundary.

When the skill workspace is not a git repository, the successful-run autocommit
safety net cannot commit. The design (publish/native-fs F1) treats this as a
benign boundary: it must NOT error, NOT block, and must NOT falsely report the
run as 'committed'. It surfaces an explicit ``git_status="no_git"``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.models.runs import RunMetadata
from app.services.git_local import GitLocalService
from app.services.run_manager import RunManager, RunRecord


def _metadata() -> RunMetadata:
    return RunMetadata(
        run_id="run-1",
        status="success",
        started_at=datetime.now(tz=UTC),
    )


def _record(run_dir: Path, metadata: RunMetadata) -> RunRecord:
    return RunRecord(
        metadata=metadata,
        skill_id="text-segmentation",
        run_dir=run_dir,
        process=None,
        process_queue=None,
    )


def test_run_metadata_accepts_no_git_status() -> None:
    metadata = RunMetadata(
        run_id="run-1",
        status="success",
        started_at=datetime.now(tz=UTC),
        git_status="no_git",
    )
    assert metadata.git_status == "no_git"


def test_successful_run_in_non_git_workspace_reports_no_git_without_error(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "text-segmentation"
    run_dir = skill_dir / ".workspace" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    assert not (skill_dir / ".git").exists()

    manager = RunManager()
    manager.git_service = GitLocalService()
    metadata = _metadata()
    record = _record(run_dir, metadata)

    updated = asyncio.run(manager._auto_commit_successful_run(record, metadata))

    assert updated.git_status == "no_git"


def test_auto_commit_run_returns_none_when_workspace_is_not_git(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    service = GitLocalService()

    assert service.auto_commit_run(skill_dir, "run-1") is None


@pytest.mark.parametrize("git_status", ["committed", "locked", "failed", "no_git"])
def test_git_status_literal_round_trips_through_run_metadata(git_status: str) -> None:
    metadata = RunMetadata(
        run_id="run-1",
        status="success",
        started_at=datetime.now(tz=UTC),
        git_status=git_status,  # type: ignore[arg-type]
    )
    assert metadata.model_dump()["git_status"] == git_status
