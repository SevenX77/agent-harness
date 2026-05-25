from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from app.services import predictor as predictor_module
from app.services.predictor import (
    MAX_PHASE_REVISITS,
    PredictDeadlockError,
    PredictorService,
)
from graph_agent.core._predict_internal.models import PathDiff
from graph_agent.core._predict_internal.strategy import GoldenCaseStrategy, HeuristicStubStrategy


@pytest.fixture(autouse=True)
def _isolate_studio_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


def _raw_result(*, actual_path: list[str] | None = None) -> dict[str, object]:
    return {
        "context": {
            "predict_trace": [
                {
                    "phase_name": "draft",
                    "type": "llm",
                    "inputs": {"topic": "predict"},
                    "outputs": {"text": "<mock_text>"},
                    "mocked_source": "heuristic_stub",
                }
            ],
            "actual_path": actual_path or ["draft"],
        }
    }


def _golden_file(tmp_path: Path, *, prompt_hash: str = "old") -> Path:
    payload = {
        "inputs": {"topic": "predict"},
        "metadata": {
            "phase_name": "draft",
            "prompt_hash": prompt_hash,
            "io_outputs_schema_hash": "schema-old",
            "expected_path": ["draft", "finish"],
        },
        "expected_traces": {"draft": {"text": "golden"}},
    }
    path = tmp_path / "case.golden.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resolve_fill_strategy_dispatches_mock_param(tmp_path: Path) -> None:
    service = PredictorService()

    assert isinstance(service.resolve_fill_strategy(None), HeuristicStubStrategy)
    assert isinstance(service.resolve_fill_strategy(_golden_file(tmp_path)), GoldenCaseStrategy)


def test_assemble_trace_marks_failed_when_path_diff_has_missing_extra_or_order() -> None:
    service = PredictorService()
    result = service.assemble_trace(
        _raw_result(),
        PathDiff(
            expected_path=["draft", "review"],
            actual_path=["draft", "debug"],
            missing=["review"],
            extra=["debug"],
        ),
    )

    assert result.status == "failed"
    assert result.path_diff is not None
    assert result.path_diff.missing == ["review"]
    assert result.phases[0].mocked_source == "heuristic_stub"


def test_assemble_trace_keeps_success_when_path_diff_is_clean() -> None:
    service = PredictorService()
    result = service.assemble_trace(
        _raw_result(),
        PathDiff(expected_path=["draft"], actual_path=["draft"]),
    )

    assert result.status == "success"


def test_dispatch_p2_none_runs_with_mock_llm_and_returns_predict_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    def fake_run_skill(skill_path: Path, **kwargs: object) -> dict[str, object]:
        calls.append({"skill_path": skill_path, **kwargs})
        return _raw_result(actual_path=["draft"])

    service = PredictorService(run_skill_fn=fake_run_skill)

    result = service.dispatch_predict_job(
        "skill",
        None,
        input_data={"topic": "predict"},
    )

    assert result.status == "success"
    assert calls[0]["mock_llm"] is None
    assert calls[0]["topic"] == "predict"


def test_dispatch_path_warns_on_hash_mismatch_but_does_not_abort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    golden_path = _golden_file(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    def fake_run_skill(skill_path: Path, **kwargs: object) -> dict[str, object]:
        del skill_path, kwargs
        return _raw_result(actual_path=["draft", "debug"])

    service = PredictorService(run_skill_fn=fake_run_skill)

    with caplog.at_level(logging.WARNING):
        result = service.dispatch_predict_job(
            "skill",
            golden_path,
            current_hashes={
                "draft": {"prompt_hash": "new", "io_outputs_schema_hash": "schema-new"}
            },
        )

    assert result.status == "failed"
    assert result.path_diff is not None
    assert result.path_diff.missing == ["finish"]
    assert result.path_diff.extra == ["debug"]
    assert any("Golden case hash stale" in record.message for record in caplog.records)


def test_dispatch_p2_deadlock_raises_with_actual_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)
    actual_path = ["draft"] * (MAX_PHASE_REVISITS + 1)

    def fake_run_skill(skill_path: Path, **kwargs: object) -> dict[str, object]:
        del skill_path, kwargs
        return _raw_result(actual_path=actual_path)

    service = PredictorService(run_skill_fn=fake_run_skill)

    with pytest.raises(PredictDeadlockError) as exc_info:
        service.dispatch_predict_job("skill", None)

    assert exc_info.value.phase_name == "draft"
    assert exc_info.value.actual_path == actual_path


def test_dispatch_p0_does_not_apply_deadlock_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    golden_path = _golden_file(tmp_path)
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    def fake_run_skill(skill_path: Path, **kwargs: object) -> dict[str, object]:
        del skill_path, kwargs
        return _raw_result(actual_path=["draft"] * (MAX_PHASE_REVISITS + 1))

    service = PredictorService(run_skill_fn=fake_run_skill)

    result = service.dispatch_predict_job("skill", golden_path)

    assert result.status == "failed"
    assert result.path_diff is not None


def test_dispatch_p1_override_does_not_apply_deadlock_guard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\n", encoding="utf-8")
    monkeypatch.setattr(predictor_module, "ensure_workspace_skill_dir", lambda skill_id: skill_dir)

    def fake_run_skill(skill_path: Path, **kwargs: object) -> dict[str, object]:
        del skill_path, kwargs
        return _raw_result(actual_path=["draft"] * (MAX_PHASE_REVISITS + 1))

    service = PredictorService(run_skill_fn=fake_run_skill)

    result = service.dispatch_predict_job("skill", {"draft": {"text": "manual"}})

    assert result.status == "success"
