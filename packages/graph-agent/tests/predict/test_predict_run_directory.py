from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from graph_agent.core import runner as runner_module
from graph_agent.io.run_layout import PREDICTS_DIRNAME, RUNS_DIRNAME, predicts_root, runs_root


class _FakeGraph:
    def invoke(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"data": SimpleNamespace(model_dump=lambda: {})}


class _FakeAssembler:
    def __init__(self) -> None:
        self.graph = _FakeGraph()


def _write_empty_v030_skill(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases: []
---
""",
        encoding="utf-8",
    )
    return root


@pytest.fixture(autouse=True)
def _stub_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "graph_agent.core.compiler.compile_skill",
        lambda *_args, **_kwargs: SimpleNamespace(nodes=[], raw={}),
    )
    monkeypatch.setattr(
        "graph_agent.core.graph_assembler.assemble_graph",
        lambda *_args, **_kwargs: _FakeAssembler(),
    )


def test_run_layout_names_two_roots(tmp_path: Path) -> None:
    """A run and a rehearsal are different things and get different homes."""
    workspace = tmp_path / ".workspace"

    assert runs_root(workspace) == workspace / RUNS_DIRNAME
    assert predicts_root(workspace) == workspace / PREDICTS_DIRNAME
    assert runs_root(workspace) != predicts_root(workspace)


def test_predict_writes_its_trace_under_predicts(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """A predict is a rehearsal; it must not leave anything in the runs root."""
    skill_root = _write_empty_v030_skill(tmp_path / "skill")
    workspace = tmp_path / ".workspace"

    runner_module.predict_skill(
        skill_root,
        workspace_dir=workspace,
        thread_id="predict-2026-08-09T13-40-42_80960a2c",
        skill_resolver=mock_skill_resolver,
    )

    assert (workspace / PREDICTS_DIRNAME / "predict-2026-08-09T13-40-42_80960a2c" / "trace.jsonl").is_file()
    assert not (workspace / RUNS_DIRNAME).exists()


def test_a_real_run_still_writes_its_trace_under_runs(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """The rehearsal moving out must not move the real thing with it."""
    skill_root = _write_empty_v030_skill(tmp_path / "skill")
    workspace = tmp_path / ".workspace"

    runner_module._run_v030_skill_dict(
        skill_root,
        workspace_dir=workspace,
        run_root=runs_root(workspace),
        thread_id="2026-08-09T13-40-42_80960a2c",
        skill_resolver=mock_skill_resolver,
    )

    assert (workspace / RUNS_DIRNAME / "2026-08-09T13-40-42_80960a2c" / "trace.jsonl").is_file()
    assert not (workspace / PREDICTS_DIRNAME).exists()


def test_the_executor_demands_a_run_root_rather_than_assuming_one(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    """Guessing the root is how a predict ends up filed as a run.

    The parameter is required so a future caller has to say which root it means
    instead of silently inheriting whichever one happened to be the default.
    """
    skill_root = _write_empty_v030_skill(tmp_path / "skill")

    with pytest.raises(TypeError, match="run_root"):
        runner_module._run_v030_skill_dict(
            skill_root,
            workspace_dir=tmp_path / ".workspace",
            skill_resolver=mock_skill_resolver,
        )
