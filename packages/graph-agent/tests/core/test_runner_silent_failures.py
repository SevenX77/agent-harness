from __future__ import annotations

import builtins
import sys
from pathlib import Path
from typing import Any

import pytest
from graph_agent.callbacks.events import ThreadCleanedUpEvent
from graph_agent.core import runner
from graph_agent.core.exceptions import LoaderError
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState


class _FailingRunHarness:
    phases: list[object] = []
    callbacks: list[object] = []

    def run(self, **kwargs: Any) -> object:
        raise RuntimeError("workflow failed")


class _FailingDeleteThreadCheckpointer:
    def delete_thread(self, thread_id: str) -> None:
        raise OSError(f"delete failed for {thread_id}")


class _RecordingDeleteThreadCheckpointer:
    def __init__(self) -> None:
        self.deleted_thread_ids: list[str] = []

    def list(self, config: dict[str, Any]) -> list[object]:
        assert config == {"configurable": {"thread_id": "thread-1"}}
        return [object(), object()]

    def delete_thread(self, thread_id: str) -> None:
        self.deleted_thread_ids.append(thread_id)


class _RecordingCallback:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _final_state() -> WorkflowState:
    return WorkflowState(
        data=BusinessData.model_validate({"result": "ok"}),
        flow=FrameworkState(
            metrics={"total_input_tokens": 0, "total_output_tokens": 0},
            trace_path=None,
        ),
        messages=[],
    )


class _SuccessfulHarness:
    phases: list[object] = []
    callbacks: list[object] = []
    _checkpointer = _FailingDeleteThreadCheckpointer()

    def run(self, **kwargs: Any) -> WorkflowState:
        return _final_state()


class _SuccessfulRecordingHarness:
    phases: list[object] = []

    def __init__(self, checkpointer: _RecordingDeleteThreadCheckpointer) -> None:
        self.callbacks: list[object] = []
        self._checkpointer = checkpointer

    def run(self, **kwargs: Any) -> WorkflowState:
        return _final_state()


def _write_skill(tmp_path: Path) -> Path:
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("# test skill\n", encoding="utf-8")
    return skill_path


def test_run_id_cleanup_failure_raises_persistence_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
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

    result = runner.run_skill(
        skill_path, output_dir=str(output_dir), skill_resolver=mock_skill_resolver
    )

    assert result.success is False
    assert result.error is not None
    assert "run_id cleanup failed: permission denied" in result.error


def test_checkpoint_cleanup_failure_warns_and_keeps_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_skill_resolver: object,
) -> None:
    skill_path = _write_skill(tmp_path)

    runner.clear_cache()
    monkeypatch.setattr(
        runner,
        "load_workflow_from_md",
        lambda *args, **kwargs: _SuccessfulHarness(),
    )

    result = runner.run_skill(skill_path, thread_id="thread-1", skill_resolver=mock_skill_resolver)

    assert result.success is True
    assert result.error is None
    assert "checkpoint cleanup failed: delete failed for thread-1" in caplog.text


def test_cleanup_on_success_deletes_thread_and_emits_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    skill_path = _write_skill(tmp_path)
    checkpointer = _RecordingDeleteThreadCheckpointer()
    callback = _RecordingCallback()

    runner.clear_cache()
    monkeypatch.setattr(
        runner,
        "load_workflow_from_md",
        lambda *args, **kwargs: _SuccessfulRecordingHarness(checkpointer),
    )

    result = runner.run_skill(
        skill_path,
        callbacks=[callback],
        thread_id="thread-1",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is True
    assert checkpointer.deleted_thread_ids == ["thread-1"]
    cleanup_events = [e for e in callback.events if isinstance(e, ThreadCleanedUpEvent)]
    assert len(cleanup_events) == 1
    assert cleanup_events[0].thread_id == "thread-1"
    assert cleanup_events[0].checkpoint_count_at_cleanup == 2


def test_no_cleanup_on_failure_preserves_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_skill_resolver: object,
) -> None:
    skill_path = _write_skill(tmp_path)
    checkpointer = _RecordingDeleteThreadCheckpointer()

    failing_harness = _FailingRunHarness()
    failing_harness._checkpointer = checkpointer

    runner.clear_cache()
    monkeypatch.setattr(
        runner,
        "load_workflow_from_md",
        lambda *args, **kwargs: failing_harness,
    )

    with pytest.raises(RuntimeError, match="workflow failed"):
        runner.run_skill(skill_path, thread_id="thread-1", skill_resolver=mock_skill_resolver)

    assert checkpointer.deleted_thread_ids == []


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
