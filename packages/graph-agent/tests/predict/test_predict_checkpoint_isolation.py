from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.core import runner as runner_module


class _DumpData:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeGraph:
    def invoke(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"data": _DumpData({"text": "ok"})}


class _FakeAssembler:
    graph = _FakeGraph()


def _write_logic_skill(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: checkpoint_isolation
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
phases:
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
        encoding="utf-8",
    )
    phase_dir = root / "phases" / "draft"
    actions_dir = phase_dir / "actions"
    actions_dir.mkdir(parents=True)
    (phase_dir / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
actions: [draft]
validator: false
---
<action>draft</action>
""",
        encoding="utf-8",
    )
    (actions_dir / "draft.py").write_text(
        "def draft(inputs):\n"
        "    return {'text': 'real-run-output'}\n",
        encoding="utf-8",
    )
    return root


def _checkpoint_rows_for_thread(db_path: Path, thread_id: str) -> int:
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'")
        if cursor.fetchone() is None:
            return 0
        cursor.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (thread_id,))
        return int(cursor.fetchone()[0])


def test_predict_passes_checkpointer_spec_none(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_logic_skill(tmp_path / "skill")
    observed_specs: list[Any] = []
    observed_resolved: list[Any] = []

    def fake_resolve_checkpointer(spec: Any = "auto") -> Any:
        observed_specs.append(spec)
        resolved = object() if spec is not None else None
        observed_resolved.append(resolved)
        return resolved

    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(nodes=[], raw={}),
    )
    monkeypatch.setattr(
        "graph_agent.core.checkpointer.resolve_checkpointer",
        fake_resolve_checkpointer,
    )
    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.assemble_graph",
        lambda *_args, **_kwargs: _FakeAssembler(),
    )

    result = runner_module.predict_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is True
    assert observed_specs == [None]
    assert observed_resolved == [None]


def test_predict_does_not_pollute_real_run_checkpoint_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    from graph_agent.core.checkpointer import reset_checkpointer

    skill_root = _write_logic_skill(tmp_path / "skill")
    db_path = tmp_path / "checkpoints.sqlite"
    thread_id = "shared-thread"
    monkeypatch.setenv("STUDIO_CHECKPOINTER", f"sqlite:{db_path}")
    reset_checkpointer()

    try:
        predict_result = runner_module.predict_skill(
            skill_root,
            workspace_dir=tmp_path / "workspace-predict",
            thread_id=thread_id,
            skill_resolver=mock_skill_resolver,
        )

        assert predict_result.source == "predict"
        assert _checkpoint_rows_for_thread(db_path, thread_id) == 0

        raw_run = runner_module._run_v030_skill_dict(
            skill_root,
            workspace_dir=tmp_path / "workspace-run",
            thread_id=thread_id,
            skill_resolver=mock_skill_resolver,
            checkpointer_spec="auto",
        )

        assert raw_run["context"]["text"] == "real-run-output"
        assert _checkpoint_rows_for_thread(db_path, thread_id) > 0
    finally:
        reset_checkpointer()


def test_predict_no_checkpointer_hitl_path_is_none_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_logic_skill(tmp_path / "skill")
    active_checkpointers: list[Any] = []
    original_find_hitl = runner_module._find_hitl_interrupt_checkpoint

    def recording_find_hitl(active_checkpointer: Any, run_id: str, result: Any) -> Any:
        active_checkpointers.append(active_checkpointer)
        return original_find_hitl(active_checkpointer, run_id, result)

    monkeypatch.setattr(runner_module, "_find_hitl_interrupt_checkpoint", recording_find_hitl)

    result = runner_module.predict_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
    )

    assert result.success is True
    assert active_checkpointers == [None]
