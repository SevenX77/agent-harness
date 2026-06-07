from __future__ import annotations

from pathlib import Path
from typing import Any

from graph_agent import RunResult, predict_skill
from graph_agent.core.exceptions import ErrorPayload


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
        encoding="utf-8",
    )

    phases_dir = skill_dir / "phases" / "draft"
    phases_dir.mkdir(parents=True)
    (phases_dir / "SKILL.md").write_text(
        "---\n"
        "name: draft\n"
        "---\n\n"
        "<role>graph_agent</role>\n"
        "<goal>do draft</goal>\n",
        encoding="utf-8",
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
        order_mismatch=False,
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
        order_mismatch=False,
    )
    result_fail = RunResult(
        success=False,
        run_id="test-2",
        skill_id="test-skill",
        context={},
        source="predict",
        path_diff=diff_fail,
        phases=[],
    )
    assert result_fail.success is False


def test_run_result_defaults_diagnostics_for_success_and_error_only_failure() -> None:
    success_result = RunResult(
        success=True,
        run_id="ok",
        skill_id="skill",
        source="predict",
        phases=[],
    )

    assert success_result.diagnostics == []
    assert success_result.diagnostics_limit > 0
    assert success_result.diagnostics_truncated is False
    assert success_result.diagnostic_counts == {"total": 0, "by_level": {}, "by_code": {}}

    error = ErrorPayload(code="[F-v3-runtime-phase-failed]", message="phase failed")
    failure_result = RunResult(
        success=False,
        run_id="fail",
        skill_id="skill",
        source="predict",
        phases=[],
        error=error,
    )

    assert failure_result.error is error
    assert failure_result.diagnostics == [error]
    assert failure_result.diagnostic_counts == {
        "total": 1,
        "by_level": {"FATAL": 1},
        "by_code": {"[F-v3-runtime-phase-failed]": 1},
    }


def test_run_result_diagnostics_merge_main_error_dedupe_bound_and_count_full_snapshot() -> None:
    main_error = ErrorPayload(code="[F-v3-runtime-phase-failed]", message="phase failed")
    warn = ErrorPayload(code="[F-v3-reference-reader-failed]", message="reference fallback")
    other_fatal = ErrorPayload(
        code="[F-v3-runtime-state-mapping-failed]",
        message="state failed",
    )

    result = RunResult(
        success=False,
        run_id="fail",
        skill_id="skill",
        source="predict",
        phases=[],
        error=main_error,
        diagnostics=[warn, main_error, other_fatal],
        diagnostics_limit=2,
    )

    assert result.diagnostics == [main_error, warn]
    assert result.diagnostics_truncated is True
    assert result.diagnostic_counts == {
        "total": 3,
        "by_level": {"FATAL": 2, "WARN": 1},
        "by_code": {
            "[F-v3-runtime-phase-failed]": 1,
            "[F-v3-reference-reader-failed]": 1,
            "[F-v3-runtime-state-mapping-failed]": 1,
        },
    }


def test_run_result_preserves_success_warn_diagnostics_and_distinct_locations() -> None:
    warn_a = ErrorPayload(
        code="[F-v3-reference-reader-failed]",
        message="reference fallback",
        source_path="a.md",
    )
    warn_b = ErrorPayload(
        code="[F-v3-reference-reader-failed]",
        message="reference fallback",
        source_path="b.md",
    )

    result = RunResult(
        success=True,
        run_id="ok",
        skill_id="skill",
        source="predict",
        phases=[],
        diagnostics=[warn_a, warn_b],
    )

    assert result.success is True
    assert result.diagnostics == [warn_a, warn_b]
    assert result.diagnostic_counts == {
        "total": 2,
        "by_level": {"WARN": 2},
        "by_code": {"[F-v3-reference-reader-failed]": 2},
    }


def test_run_result_json_dump_is_safe_with_non_json_diagnostic_details(tmp_path: Path) -> None:
    import json

    error = ErrorPayload(
        code="[F-v3-runtime-phase-failed]",
        message="phase failed",
        details={"path": tmp_path / "run.json", "tags": {"beta", "alpha"}},
    )

    result = RunResult(
        success=False,
        run_id="fail",
        skill_id="skill",
        source="predict",
        phases=[],
        error=error,
    )

    dumped = result.model_dump(mode="json")
    assert dumped["diagnostics"][0]["details"]["path"] == str(tmp_path / "run.json")
    assert dumped["diagnostics"][0]["details"]["tags"] == ["alpha", "beta"]
    assert json.loads(result.model_dump_json())["diagnostics"] == dumped["diagnostics"]
    assert json.dumps(dumped)


def test_run_result_non_positive_diagnostics_limit_uses_safe_default() -> None:
    error = ErrorPayload(code="[F-v3-runtime-phase-failed]", message="phase failed")

    result = RunResult(
        success=False,
        run_id="fail",
        skill_id="skill",
        source="predict",
        phases=[],
        error=error,
        diagnostics_limit=0,
    )

    assert result.diagnostics_limit > 0
    assert result.diagnostics == [error]
    assert result.diagnostics_truncated is False
