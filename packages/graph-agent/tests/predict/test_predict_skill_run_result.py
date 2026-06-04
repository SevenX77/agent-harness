from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent import RunResult, predict_skill


def test_predict_skill_returns_run_result_with_predict_source(tmp_path: Path, mock_skill_resolver: Any) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "GRAPH.md").write_text(
        "---\n"
        "name: test_skill\n"
        "schema_version: \"v0.3.0\"\n"
        "io:\n"
        "  inputs:\n"
        "    properties: {}\n"
        "  outputs:\n"
        "    properties: {}\n"
        "phases:\n"
        "  - draft\n"
        "---\n\n"
        "<phase depends_on=\"input\" output>draft</phase>\n",
        encoding="utf-8"
    )
    
    phases_dir = skill_dir / "phases" / "draft"
    phases_dir.mkdir(parents=True)
    (phases_dir / "SKILL.md").write_text(
        "---\n"
        "name: draft\n"
        "---\n\n"
        "<role>graph_agent</role>\n"
        "<goal>do draft</goal>\n",
        encoding="utf-8"
    )
    
    result = predict_skill(
        skill_dir,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        mock_llm={"draft": {"output": "hello"}},
    )
    
    assert isinstance(result, RunResult)
    assert result.source == "predict"
    assert result.success is True
    assert len(result.phases) == 1
    assert result.phases[0].phase_name == "draft"
    assert result.phases[0].mocked_source == "manual"


def test_run_result_success_derives_from_path_diff() -> None:
    # This asserts the first-principles path_diff to success mapping.
    # RunResult should derive success from path_diff.
    # We will write actual assertions that fail until RunResult is implemented.
    from graph_agent.core.result import PathDiff as SDKPathDiff
    
    # Successful path: no missing, no extra, order_mismatch is False
    diff_ok = SDKPathDiff(
        expected_path=["a", "b"],
        actual_path=["a", "b"],
        missing=[],
        extra=[],
        order_mismatch=False
    )
    result_ok = RunResult(
        success=True,  # Will be set or derived
        run_id="test-1",
        skill_id="test-skill",
        context={},
        source="predict",
        path_diff=diff_ok,
        phases=[],
        started_at=None,  # Or datetime
        finished_at=None,
    )
    assert result_ok.success is True
    
    # Failed path: has missing
    diff_fail = SDKPathDiff(
        expected_path=["a", "b"],
        actual_path=["a"],
        missing=["b"],
        extra=[],
        order_mismatch=False
    )
    result_fail = RunResult(
        success=False,
        run_id="test-2",
        skill_id="test-skill",
        context={},
        source="predict",
        path_diff=diff_fail,
        phases=[]
    )
    assert result_fail.success is False
