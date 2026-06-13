from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.adapter_contracts import (
    PredictArtifactRequest,
    RunArtifactRequest,
    RunSession,
)
from graph_agent.core.artifacts import ArtifactRef, compile_artifact


class CountingArtifactExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: RunArtifactRequest) -> dict[str, Any]:
        self.calls += 1
        return {"artifact_id": request.artifact_ref.artifact_id, "calls": self.calls}


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact-runtime-demo",
        content_hash="sha256:runtime-demo",
        store="ephemeral",
        manifest_ref="object://manifest.json",
        source_map_ref="object://source-map.json",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_two_phase_logic_skill(root: Path) -> None:
    _write_text(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: artifact-runtime-real-graph
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: string
      answer:
        type: string
phases:
  - prepare
  - draft
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>draft</phase>
""",
    )
    _write_text(
        root / "phases" / "prepare" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: string
---
<action>prepare</action>
""",
    )
    _write_text(
        root / "phases" / "prepare" / "actions" / "prepare.py",
        "def prepare(context):\n"
        "    return {'prepared': 'prepared:' + str(context.get('topic', 'missing'))}\n",
    )
    _write_text(
        root / "phases" / "draft" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      prepared:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
---
<action>draft</action>
""",
    )
    _write_text(
        root / "phases" / "draft" / "actions" / "draft.py",
        "def draft(context):\n"
        "    return {'answer': 'answer:' + str(context.get('prepared', 'missing'))}\n",
    )


def test_run_artifact_accepts_artifact_ref_and_returns_run_session() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-run-artifact-1",
    )

    session = runner.run_artifact(request, artifact_executor=CountingArtifactExecutor())

    assert session.run_id
    assert session.event_stream_ref


def test_core_run_artifact_rejects_raw_skill_path() -> None:
    runner = importlib.import_module("graph_agent.core.runner")

    assert hasattr(runner, "run_artifact"), "Engine must expose run_artifact before it can reject raw skill_path"

    with pytest.raises(Exception) as exc_info:
        runner.run_artifact(
            skill_path="/tmp/legacy/SKILL.md",
            inputs={"topic": "red"},
            idempotency_key="idem-raw-path",
        )

    assert getattr(exc_info.value, "error_code", None) == "runtime.raw_skill_path"


def test_run_artifact_idempotency_key_executes_once() -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    executor = CountingArtifactExecutor()
    request = RunArtifactRequest(
        artifact_ref=_artifact_ref(),
        inputs={"topic": "red"},
        execution_context={"workspace_id": "local"},
        idempotency_key="idem-repeat",
    )

    first = runner.run_artifact(request, artifact_executor=executor)
    second = runner.run_artifact(request, artifact_executor=executor)

    assert first.run_id == second.run_id
    assert executor.calls == 1


def test_run_artifact_without_executor_executes_compiled_graph(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"

    request = RunArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "mars"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-run",
        },
        idempotency_key="idem-real-graph-run",
    )

    session = runner.run_artifact(request, skill_resolver=mock_skill_resolver)

    assert isinstance(session, RunSession)
    result_path = workspace_dir / "runs" / session.run_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["success"] is True
    assert result["context"]["prepared"] == "prepared:mars"
    assert result["context"]["answer"] == "answer:prepared:mars"


def test_predict_artifact_without_executor_executes_predict_graph_with_mock(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    runner = importlib.import_module("graph_agent.core.runner")
    skill_root = tmp_path / "artifact-runtime-real-graph"
    _write_two_phase_logic_skill(skill_root)
    manifest = compile_artifact(source_root=skill_root, skill_resolver=mock_skill_resolver)
    workspace_dir = tmp_path / "workspace"

    request = PredictArtifactRequest(
        artifact_ref=manifest.artifact_ref,
        inputs={"topic": "venus"},
        execution_context={
            "artifact_root": str(skill_root),
            "workspace_dir": str(workspace_dir),
            "thread_id": "artifact-real-predict",
            "mock_llm": {"draft": {"answer": "mocked-answer"}},
        },
        idempotency_key="idem-real-graph-predict",
    )

    session = runner.predict_artifact(request, skill_resolver=mock_skill_resolver)

    assert isinstance(session, RunSession)
    result_path = workspace_dir / "runs" / session.run_id / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["source"] == "predict"
    assert result["context"]["prepared"] == "prepared:venus"
    assert result["context"]["answer"] == "answer:prepared:venus"
    assert [phase["phase_name"] for phase in result["phases"]] == ["prepare", "draft"]
