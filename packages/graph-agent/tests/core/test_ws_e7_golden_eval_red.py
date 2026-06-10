"""RED tests for WS-E7 Engine golden evaluation contracts."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

import graph_agent
from graph_agent.core.compiler import compile_skill


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _public_callable(name: str) -> Callable[..., Any]:
    value = getattr(graph_agent, name, None)
    assert callable(value), f"graph_agent.{name} must be a public callable"
    return value


def _as_report(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload)


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    payload: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        payload["required"] = required
    return json.dumps(payload, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _logic_skill(root: Path, *, required_outputs: list[str] | None = None) -> None:
    outputs: dict[str, Any] = {
        "answer": {"type": "string"},
    }
    if required_outputs and "confidence" in required_outputs:
        outputs["confidence"] = {"type": "number"}
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e7-golden-eval-red
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema(outputs, required=required_outputs or ["answer"])}
phases:
  - score
---
<phase depends_on="input" output>score</phase>
""",
    )
    _write(
        root / "phases" / "score" / "LOGIC.md",
        f"""---
io:
  inputs:
    {_schema({"topic": {"type": "string"}}, required=["topic"])}
  outputs:
    {_schema(outputs, required=required_outputs or ["answer"])}
actions: [score]
validator: false
---
<action>score</action>
""",
    )
    confidence_line = '"confidence": 0.9,' if required_outputs and "confidence" in required_outputs else ""
    _write(
        root / "phases" / "score" / "actions" / "score.py",
        dedent(
            f"""
            def score(context):
                return {{
                    "answer": f"score:{{context['topic']}}",
                    {confidence_line}
                }}
            """
        ).lstrip(),
    )


def _case(
    *,
    case_id: str,
    phase_id: str = "score",
    topic: str = "alpha",
    expected_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "phase_id": phase_id,
        "inputs": {"topic": topic},
        "expected_output": expected_output or {"answer": f"score:{topic}"},
        "source": "manual",
        "updated_at": "2026-06-10T00:00:00Z",
    }


def _golden_baseline(workspace_dir: Path, baseline_id: str, cases: list[dict[str, Any]]) -> None:
    baseline_dir = workspace_dir / "golden" / baseline_id
    _write_json(
        baseline_dir / "baseline.json",
        {
            "baseline_id": baseline_id,
            "created_at": "2026-06-10T00:00:00Z",
            "case_ids": [case["case_id"] for case in cases],
        },
    )
    for case in cases:
        _write_json(baseline_dir / "cases" / f"{case['case_id']}.json", case)


def test_evaluate_golden_baseline_public_api_signature_is_locked() -> None:
    evaluate = _public_callable("evaluate_golden_baseline")
    signature = inspect.signature(evaluate)

    assert signature.parameters["workspace_dir"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["workspace_dir"].default is inspect.Signature.empty
    assert signature.parameters["baseline_id"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["baseline_id"].default is inspect.Signature.empty
    assert signature.parameters["skill_resolver"].default is inspect.Signature.empty


def test_evaluate_golden_rejects_relative_workspace_dir(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _logic_skill(tmp_path / "skill")
    _golden_baseline(tmp_path / "workspace", "baseline-a", [_case(case_id="case-a")])
    evaluate = _public_callable("evaluate_golden_baseline")

    with pytest.raises((TypeError, ValueError), match="workspace_dir"):
        evaluate(
            tmp_path / "skill",
            workspace_dir=Path("relative-workspace"),
            baseline_id="baseline-a",
            skill_resolver=mock_skill_resolver,
        )


def test_deterministic_logic_case_exact_match_writes_passed_report(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    baseline_id = "baseline-pass"
    _logic_skill(skill_root)
    _golden_baseline(workspace_dir, baseline_id, [_case(case_id="case-pass", topic="alpha")])

    evaluate = _public_callable("evaluate_golden_baseline")
    report = _as_report(
        evaluate(
            skill_root,
            workspace_dir=workspace_dir,
            baseline_id=baseline_id,
            skill_resolver=mock_skill_resolver,
        )
    )

    assert report["baseline_id"] == baseline_id
    assert report["summary"] == {"total_cases": 1, "passed": 1, "failed": 0, "stale": 0}
    assert report["cases"][0]["case_id"] == "case-pass"
    assert report["cases"][0]["phase_id"] == "score"
    assert report["cases"][0]["status"] == "passed"
    assert report["cases"][0]["score"] == 1.0
    assert report["cases"][0]["diff"] == []
    assert report["cases"][0]["stale_fields"] == []
    assert json.loads((workspace_dir / "golden" / baseline_id / "report.json").read_text()) == report


def test_golden_value_mismatch_returns_failed_case_with_field_diff(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    baseline_id = "baseline-failed"
    _logic_skill(skill_root)
    _golden_baseline(
        workspace_dir,
        baseline_id,
        [_case(case_id="case-failed", topic="alpha", expected_output={"answer": "wrong"})],
    )

    evaluate = _public_callable("evaluate_golden_baseline")
    report = _as_report(
        evaluate(
            skill_root,
            workspace_dir=workspace_dir,
            baseline_id=baseline_id,
            skill_resolver=mock_skill_resolver,
        )
    )

    case = report["cases"][0]
    assert report["summary"] == {"total_cases": 1, "passed": 0, "failed": 1, "stale": 0}
    assert case["status"] == "failed"
    assert case["score"] < 1.0
    assert case["stale_fields"] == []
    assert case["diff"] == [
        {
            "path": "answer",
            "expected": "wrong",
            "actual": "score:alpha",
            "status": "changed",
        }
    ]


def test_required_output_missing_from_expected_marks_case_stale_not_compile_fatal(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    baseline_id = "baseline-stale"
    _logic_skill(skill_root, required_outputs=["answer", "confidence"])
    _golden_baseline(
        workspace_dir,
        baseline_id,
        [_case(case_id="case-stale", topic="alpha", expected_output={"answer": "score:alpha"})],
    )

    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    assert compiled is not None

    evaluate = _public_callable("evaluate_golden_baseline")
    report = _as_report(
        evaluate(
            skill_root,
            workspace_dir=workspace_dir,
            baseline_id=baseline_id,
            skill_resolver=mock_skill_resolver,
        )
    )

    assert report["summary"] == {"total_cases": 1, "passed": 0, "failed": 0, "stale": 1}
    assert report["cases"][0]["status"] == "stale"
    assert report["cases"][0]["stale_fields"] == ["confidence"]


def test_golden_eval_uses_workspace_golden_not_skill_source_or_predict_latest(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    baseline_id = "baseline-layout"
    _logic_skill(skill_root)
    _golden_baseline(workspace_dir, baseline_id, [_case(case_id="case-layout")])

    assert not list(skill_root.rglob("golden.json"))
    evaluate = _public_callable("evaluate_golden_baseline")
    evaluate(
        skill_root,
        workspace_dir=workspace_dir,
        baseline_id=baseline_id,
        skill_resolver=mock_skill_resolver,
    )

    assert not list(skill_root.rglob("golden.json"))
    assert not (workspace_dir / "predict" / "latest_predict.json").exists()
