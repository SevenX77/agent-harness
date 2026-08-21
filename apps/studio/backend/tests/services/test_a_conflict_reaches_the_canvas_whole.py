"""Both participants of a two-phase conflict survive the trip to the frontend.

The engine now states a sequential-overwrite conflict in fields: which field
collides (``field_path``) and which upstream phase wrote it first
(``conflicting_phase``). The Studio shell is the only thing between that and
the canvas popover, so if it drops either axis the frontend is back to reading
the English sentence — which is exactly what ledger K3 is about.
"""

from __future__ import annotations

from pathlib import Path

from app.core.adapters.engine import GraphCompileError
from app.services import skills as skill_service
from graph_agent.core.compiler import CompileIssue, CompileResult


def _overwrite_issue() -> CompileIssue:
    return CompileIssue(
        rule_id="[F-v3-sequential-overwrite-unauthorized]",
        severity="FATAL",
        source_path="phases/revise/LOGIC.md",
        line=1,
        field_path="io.outputs.properties.summary",
        message=(
            "Phase 'revise' sequentially overwrites field 'summary' outputted by "
            "upstream phase 'draft'."
        ),
        conflicting_phase="draft",
    )


def _compile_errors(issue: CompileIssue, skill_dir: Path) -> list[object]:
    exc = GraphCompileError(issue.message)
    exc.compile_result = CompileResult(issues=[issue])  # type: ignore[attr-defined]
    return list(skill_service._compile_errors_from_exception(exc, skill_dir))


def test_the_overwritten_field_arrives_as_a_field_not_as_prose(tmp_path: Path) -> None:
    (error,) = _compile_errors(_overwrite_issue(), tmp_path)

    assert error.field == "io.outputs.properties.summary"


def test_the_upstream_phase_arrives_as_a_field_not_as_prose(tmp_path: Path) -> None:
    (error,) = _compile_errors(_overwrite_issue(), tmp_path)

    assert error.conflicting_phase == "draft"


def test_a_single_phase_diagnostic_claims_no_second_participant(tmp_path: Path) -> None:
    issue = CompileIssue(
        rule_id="[F-v3-graph-phase-island]",
        severity="FATAL",
        source_path="GRAPH.md",
        line=4,
        field_path="phases",
        message="Phase 'orphan' is unreachable.",
    )

    (error,) = _compile_errors(issue, tmp_path)

    assert error.conflicting_phase is None
