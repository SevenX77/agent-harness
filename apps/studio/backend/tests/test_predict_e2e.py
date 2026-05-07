from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from app.services import predictor as predictor_module
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.predictor import MAX_PHASE_REVISITS, PredictDeadlockError, PredictorService


def test_backend_p2_predict_job_exports_diagnostics(
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
    export = export_predict_diagnostics(result)

    assert result.status == "success"
    assert export.is_predict is True
    assert [phase.phase_name for phase in export.phases] == ["prepare", "draft"]
    assert export.phases[1].mocked_source == "heuristic_stub"


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

    result = PredictorService().dispatch_predict_job("skill", mock_llm, input_data={"topic": "mars"})

    assert result.status == "success"
    assert result.phases[1].mocked_source == expected_source


def test_backend_p0_predict_job_warns_diffs_and_uses_golden_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    golden_path = _write_golden_case(tmp_path, expected_path=["draft", "finish"])
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    with caplog.at_level(logging.WARNING):
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
    assert any("Golden case hash stale" in record.message for record in caplog.records)


def test_backend_deadlock_guard_blocks_p2_but_not_p0(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    golden_path = _write_golden_case(tmp_path, expected_path=["draft"])
    actual_path = ["draft"] * (MAX_PHASE_REVISITS + 1)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    def fake_run_skill(_skill_path: Path, **_kwargs: object) -> dict[str, object]:
        return {"context": {"actual_path": actual_path}}

    service = PredictorService(run_skill_fn=fake_run_skill)

    with pytest.raises(PredictDeadlockError):
        service.dispatch_predict_job("skill", None)

    result = service.dispatch_predict_job("skill", golden_path)
    assert result.status == "failed"
    assert result.path_diff is not None
    assert result.path_diff.actual_path == actual_path


def _write_backend_skill(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skill"
    script_dir = skill_dir / "script"
    script_dir.mkdir(parents=True)
    (script_dir / "__init__.py").write_text("", encoding="utf-8")
    (script_dir / "logic.py").write_text(
        "def prepare(ctx):\n"
        "    ctx['prepared'] = True\n"
        "    return ctx\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        """---
schema_version: "2.0"
name: predict-backend-e2e
version: "0.1"
description: Predict backend e2e smoke
type: graph
context_mapping:
  topic: "{input.topic}"
io:
  inputs:
    - name: topic
      type: str
      source: runtime
  outputs: []
phases:
  - name: prepare
    mode: logic
    execute_steps:
      - script.logic.prepare
  - name: draft
    mode: llm
    llm_role: analyst
    max_iterations: 1
    max_nudges: 0
    validator_optional: true
    output_schema: |
      text: str
    prompt: |
      Write a draft for {topic} and call finish_task.
---
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
