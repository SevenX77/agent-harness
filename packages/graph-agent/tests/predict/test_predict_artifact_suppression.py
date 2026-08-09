from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core import runner as runner_module
from graph_agent.core.exceptions import GraphAgentFatalError


def _write_artifact_skill(root: Path, *, required_missing: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    required = "[missing]" if required_missing else "[report]"
    (root / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: artifact_suppression
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    required: {required}
    properties:
      report:
        type: object
        target: file
        properties:
          message:
            type: string
      missing:
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
    required: [report]
    properties:
      report:
        type: object
      missing:
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
        "    return {'report': {'message': 'predict diagnostic only'}}\n",
        encoding="utf-8",
    )
    return root


def _all_relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _run_predict(
    skill_root: Path,
    workspace_dir: Path,
    mock_skill_resolver: Any,
    *,
    runtime_config: dict[str, Any] | None = None,
) -> Any:
    return runner_module.predict_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="predict-artifacts",
        skill_resolver=mock_skill_resolver,
        runtime_config=runtime_config,
    )


def test_predict_suppresses_declared_file_output_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_artifact_skill(tmp_path / "skill")
    workspace_dir = tmp_path / "workspace"
    calls: list[dict[str, Any]] = []
    original_save = runner_module._save_v030_declared_file_outputs

    def recording_save(*args: Any, **kwargs: Any) -> Any:
        calls.append({"args": args, "kwargs": kwargs})
        return original_save(*args, **kwargs)

    monkeypatch.setattr(runner_module, "_save_v030_declared_file_outputs", recording_save)

    result = _run_predict(skill_root, workspace_dir, mock_skill_resolver)

    assert result.success is True
    assert calls == []
    assert not (workspace_dir / "predicts" / result.run_id / "artifacts" / "report.json").exists()


def test_predict_suppresses_manifest_artifact_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_artifact_skill(tmp_path / "skill")
    workspace_dir = tmp_path / "workspace"
    calls: list[dict[str, Any]] = []
    original_write = runner_module.write_manifest_artifacts

    def recording_write(*args: Any, **kwargs: Any) -> Any:
        calls.append({"args": args, "kwargs": kwargs})
        return original_write(*args, **kwargs)

    monkeypatch.setattr(runner_module, "write_manifest_artifacts", recording_write)

    result = _run_predict(
        skill_root,
        workspace_dir,
        mock_skill_resolver,
        runtime_config={
            "artifacts": [
                {
                    "stem": "report_manifest",
                    "fields": ["report"],
                    "format": "json",
                }
            ]
        },
    )

    artifacts_dir = workspace_dir / "predicts" / result.run_id / "artifacts"
    assert result.success is True
    assert calls == []
    assert not list(artifacts_dir.glob("report_manifest_latest_*.json"))


def test_predict_still_inherits_root_output_validation(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_artifact_skill(tmp_path / "skill", required_missing=True)

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _run_predict(skill_root, tmp_path / "workspace", mock_skill_resolver)

    assert exc_info.value.payload is not None
    assert exc_info.value.payload.code == "[F-v3-runtime-state-mapping-failed]"
    assert exc_info.value.payload.field_path is None


def test_predict_never_writes_into_skill_source_dir(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_artifact_skill(tmp_path / "skill")
    before_files = _all_relative_files(skill_root)
    before_contents = {
        rel: (skill_root / rel).read_bytes()
        for rel in before_files
    }

    result = _run_predict(skill_root, tmp_path / "workspace", mock_skill_resolver)

    assert result.success is True
    assert _all_relative_files(skill_root) == before_files
    assert {
        rel: (skill_root / rel).read_bytes()
        for rel in before_files
    } == before_contents


def test_predict_diagnostic_artifacts_unchanged(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = _write_artifact_skill(tmp_path / "skill")
    workspace_dir = tmp_path / "workspace"

    result = _run_predict(skill_root, workspace_dir, mock_skill_resolver)

    run_dir = workspace_dir / "predicts" / result.run_id
    trace_path = run_dir / "trace.jsonl"
    result_path = run_dir / "result.json"
    final_state_path = run_dir / "final_state.json"
    metrics_path = run_dir / "metrics.json"

    assert trace_path.is_file()
    assert result_path.is_file()
    assert final_state_path.is_file()
    assert metrics_path.is_file()
    assert json.loads(result_path.read_text(encoding="utf-8"))["source"] == "predict"
    assert json.loads(final_state_path.read_text(encoding="utf-8"))["report"] == {
        "message": "predict diagnostic only"
    }
    assert not (run_dir / "artifacts").exists()
