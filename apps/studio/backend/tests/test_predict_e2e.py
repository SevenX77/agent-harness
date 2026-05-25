from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from app.services import predictor as predictor_module
from app.services.diagnostic_export import export_predict_diagnostics
from app.services.predictor import MAX_PHASE_REVISITS, PredictDeadlockError, PredictorService


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


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
    assert export.phases[1].mocked_source is None


@pytest.mark.parametrize(
    "mock_llm",
    [
        {"draft": {"text": "manual draft"}},
        {"draft": {"source": "copilot", "output": {"text": "copilot draft"}}},
    ],
)
def test_backend_p1_predict_job_uses_manual_or_copilot_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mock_llm: dict[str, object],
) -> None:
    skill_dir = _write_backend_skill(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    result = PredictorService().dispatch_predict_job(
        "skill", mock_llm, input_data={"topic": "mars"}
    )

    assert result.status == "success"
    assert result.phases[1].mocked_source is None


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
    assert result.phases[1].mocked_source is None
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
    action_dir = skill_dir / "phases" / "prepare" / "actions"
    action_dir.mkdir(parents=True)
    (action_dir / "__init__.py").write_text("", encoding="utf-8")
    (action_dir / "prepare.py").write_text(
        "def prepare(context):\n    context.set('prepared', True)\n    return {'prepared': True}\n",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "draft").mkdir(parents=True)
    draft_action_dir = skill_dir / "phases" / "draft" / "actions"
    draft_action_dir.mkdir(parents=True)
    (draft_action_dir / "__init__.py").write_text("", encoding="utf-8")
    (draft_action_dir / "draft.py").write_text(
        "def draft(context):\n    context.set('text', 'draft')\n    return {'text': 'draft'}\n",
        encoding="utf-8",
    )
    (skill_dir / "io").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "2.1"
name: predict-backend-e2e
description: Predict backend e2e smoke
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="prepare" src="phases/prepare" depends_on="" />
<phase id="draft" src="phases/draft" depends_on="prepare" />
""",
        encoding="utf-8",
    )
    (skill_dir / "io" / "inputs.json").write_text(
        '{"type":"object","properties":{"topic":{"type":"string"}},"additionalProperties":true}\n',
        encoding="utf-8",
    )
    (skill_dir / "io" / "outputs.json").write_text(
        '{"type":"object","properties":{"prepared":{"type":"boolean"},"text":{"type":"string"}}}\n',
        encoding="utf-8",
    )
    (skill_dir / "phases" / "prepare" / "LOGIC.md").write_text(
        """---
mode: logic
name: prepare
---
<python_callable>
prepare
</python_callable>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "draft" / "LOGIC.md").write_text(
        """---
mode: logic
name: draft
---
<python_callable>
draft
</python_callable>
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
