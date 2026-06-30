from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from app.core.adapters.engine import PathDiff, PhaseRecord, RunResult
from app.services import predictor as predictor_module
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.predictor import PredictorService


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def test_backend_predict_job_without_provider_runs_logic_artifact_graph(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    result = PredictorService().dispatch_predict_job(
        "skill",
        None,
        input_data={"topic": "mars"},
    )

    assert result.status == "success"
    assert result.context["prepared"] is True
    assert result.context["text"] == "draft"


def test_backend_predict_job_exports_diagnostics_from_artifact_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    artifact_result = _predict_result(
        phases=[
            PhaseRecord(
                phase_name="prepare",
                type="logic",
                inputs={"topic": "mars"},
                outputs={"prepared": True},
            ),
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"prepared": True},
                outputs={"text": "draft"},
            ),
        ],
    )
    calls, artifact_ref = _patch_engine_predict_artifact(monkeypatch, artifact_result)

    result = PredictorService().dispatch_predict_job("skill", None, input_data={"topic": "mars"})
    export = export_predict_diagnostics(result)

    assert result.status == "success"
    assert export.is_predict is True
    assert [phase.phase_name for phase in export.phases] == ["prepare", "draft"]
    assert export.phases[1].mocked_source is None
    assert calls[0]["artifact_ref"] == artifact_ref
    assert calls[0]["inputs"] == {"topic": "mars"}


@pytest.mark.parametrize(
    ("mock_llm", "expected_source"),
    [
        ({"draft": {"text": "manual draft"}}, "manual"),
        ({"draft": {"source": "copilot", "output": {"text": "copilot draft"}}}, "copilot"),
    ],
)
def test_backend_p1_predict_job_uses_manual_or_copilot_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_llm: dict[str, object],
    expected_source: str,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    artifact_result = _predict_result(
        phases=[
            PhaseRecord(
                phase_name="prepare",
                type="logic",
                inputs={"topic": "mars"},
                outputs={"prepared": True},
            ),
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"prepared": True},
                outputs={"text": f"{expected_source} draft"},
                mocked_source=expected_source,
            ),
        ],
    )
    calls, _artifact_ref = _patch_engine_predict_artifact(monkeypatch, artifact_result)

    result = PredictorService().dispatch_predict_job("skill", mock_llm, input_data={"topic": "mars"})

    assert result.status == "success"
    assert result.phases[1].mocked_source == expected_source
    assert calls[0]["mock_llm"] == mock_llm
    assert calls[0]["inputs"] == {"topic": "mars"}


def test_backend_p0_predict_job_passes_golden_request_to_artifact_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    golden_path = _write_golden_case(tmp_path, expected_path=["draft", "finish"])
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    artifact_result = _predict_result(
        success=False,
        phases=[
            PhaseRecord(
                phase_name="prepare",
                type="logic",
                inputs={"topic": "mars"},
                outputs={"prepared": True},
            ),
            PhaseRecord(
                phase_name="draft",
                type="llm",
                inputs={"prepared": True},
                outputs={"text": "golden draft"},
                mocked_source="golden_case",
            ),
        ],
        path_diff=PathDiff(
            expected_path=["draft", "finish"],
            actual_path=["prepare", "draft"],
            missing=["finish"],
            extra=["prepare"],
            order_mismatch=False,
        ),
    )
    calls, _artifact_ref = _patch_engine_predict_artifact(monkeypatch, artifact_result)

    result = PredictorService().dispatch_predict_job(
        "skill",
        golden_path,
        input_data={"topic": "mars"},
        current_hashes={"draft": {"prompt_hash": "new", "io_outputs_schema_hash": "new"}},
    )

    assert result.status == "failed"
    assert result.path_diff is not None
    assert result.path_diff.missing == ["finish"]
    assert result.path_diff.extra == ["prepare"]
    assert result.phases[1].mocked_source == "golden_case"
    assert calls[0]["mock_llm"] == golden_path
    assert calls[0]["current_hashes"] == {"draft": {"prompt_hash": "new", "io_outputs_schema_hash": "new"}}


def _patch_engine_predict_artifact(
    monkeypatch: pytest.MonkeyPatch,
    result: RunResult,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    import app.core.adapters.engine as engine_adapter_module

    artifact_ref = {
        "artifact_id": "skill",
        "content_hash": "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "store": "ephemeral",
        "manifest_ref": "manifest_ref",
    }
    monkeypatch.setattr(
        engine_adapter_module.EngineAdapter,
        "compile",
        lambda *args, **kwargs: artifact_ref,
    )
    calls: list[dict[str, Any]] = []

    def fake_predict_artifact(_adapter: object, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return result.model_dump(mode="json")

    monkeypatch.setattr(engine_adapter_module.EngineAdapter, "predict_artifact", fake_predict_artifact)
    return calls, artifact_ref


def _predict_result(
    *,
    success: bool = True,
    phases: list[PhaseRecord],
    path_diff: PathDiff | None = None,
) -> RunResult:
    return RunResult(
        success=success,
        run_id="predict-artifact-e2e",
        skill_id="skill",
        context={"topic": "mars"},
        source="predict",
        phases=phases,
        path_diff=path_diff,
    )


def _write_backend_skill(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skill"
    action_dir = skill_dir / "phases" / "prepare" / "actions"
    action_dir.mkdir(parents=True)
    (action_dir / "__init__.py").write_text("", encoding="utf-8")
    (action_dir / "prepare.py").write_text(
        "def prepare(inputs):\n    return {'prepared': True}\n",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "draft").mkdir(parents=True)
    draft_action_dir = skill_dir / "phases" / "draft" / "actions"
    draft_action_dir.mkdir(parents=True)
    (draft_action_dir / "__init__.py").write_text("", encoding="utf-8")
    (draft_action_dir / "draft.py").write_text(
        "def draft(inputs):\n    return {'text': 'draft'}\n",
        encoding="utf-8",
    )
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: predict-backend-e2e
description: Predict backend e2e smoke
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
    additionalProperties: true
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
      text:
        type: string
phases:
  - prepare
  - draft
---
<phase depends_on="input">prepare</phase>
<phase depends_on="prepare" output>draft</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "prepare" / "LOGIC.md").write_text(
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
        type: boolean
---
<action>prepare</action>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "draft" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties:
      prepared:
        type: boolean
  outputs:
    type: object
    properties:
      text:
        type: string
---
<action>draft</action>
""",
        encoding="utf-8",
    )
    return skill_dir


def _write_golden_case(tmp_path: Path, *, expected_path: list[str]) -> Path:
    path = tmp_path / "case.golden.json"
    path.write_text(
        json.dumps(
            {
                "inputs": {"topic": "mars"},
                "metadata": {
                    "phase_name": "draft",
                    "prompt_hash": "old-prompt",
                    "io_outputs_schema_hash": "old-schema",
                    "expected_path": expected_path,
                },
                "expected_traces": {"draft": {"text": "golden draft"}},
            }
        ),
        encoding="utf-8",
    )
    return path
