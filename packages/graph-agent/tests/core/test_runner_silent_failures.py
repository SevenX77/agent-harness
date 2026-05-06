from __future__ import annotations

import builtins
import sys
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core import runner
from graph_agent.core.exceptions import LoaderError


class _FailingRunHarness:
    phases: list[object] = []
    callbacks: list[object] = []

    def run(self, **kwargs: Any) -> object:
        raise RuntimeError("workflow failed")


class _FailingDeleteThreadCheckpointer:
    def delete_thread(self, thread_id: str) -> None:
        raise OSError(f"delete failed for {thread_id}")


class _SuccessfulHarness:
    phases: list[object] = []
    callbacks: list[object] = []
    _checkpointer = _FailingDeleteThreadCheckpointer()

    def run(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "context": {},
            "messages": [],
            "current_phase": "done",
            "retry_counts": {},
            "metrics": {"total_input_tokens": 0, "total_output_tokens": 0},
        }


def _write_skill(tmp_path: Path) -> Path:
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("# test skill\n", encoding="utf-8")
    return skill_path


def test_run_id_cleanup_failure_raises_persistence_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_path = _write_skill(tmp_path)
    output_dir = tmp_path / "out"
    original_unlink = Path.unlink

    runner.clear_cache()
    monkeypatch.setattr(
        runner,
        "load_workflow_from_md",
        lambda *args, **kwargs: _FailingRunHarness(),
    )

    def _broken_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == ".run_id":
            raise OSError("permission denied")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _broken_unlink)

    result = runner.run_skill(skill_path, output_dir=str(output_dir))

    assert result.success is False
    assert result.error is not None
    assert "run_id cleanup failed: permission denied" in result.error


def test_checkpoint_cleanup_failure_raises_persistence_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_path = _write_skill(tmp_path)

    runner.clear_cache()
    monkeypatch.setattr(
        runner,
        "load_workflow_from_md",
        lambda *args, **kwargs: _SuccessfulHarness(),
    )

    result = runner.run_skill(skill_path, thread_id="thread-1")

    assert result.success is False
    assert result.error is not None
    assert "checkpoint cleanup failed: delete failed for thread-1" in result.error


def test_main_dotenv_import_failure_raises_loader_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_path = _write_skill(tmp_path)
    original_import = builtins.__import__

    def _blocked_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "dotenv":
            raise ImportError("dotenv missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    monkeypatch.setattr(sys, "argv", ["graph-agent", "--skill", str(skill_path)])

    with pytest.raises(LoaderError) as exc_info:
        runner.main()

    assert "required import failed: dotenv missing" in str(exc_info.value)
    assert exc_info.value.context == {"module": "dotenv"}
    assert isinstance(exc_info.value.__cause__, ImportError)
