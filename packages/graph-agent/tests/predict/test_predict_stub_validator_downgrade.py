"""Predict with a P2 placeholder stub must not die on an author phase validator.

Decision doc: .kiro/specs/decision-2026-08-15-predict-stub-validator-downgrade.md

A placeholder stub synthesizes schema-conform but semantically fabricated output.
An author validator that checks semantics (this segment must cover exactly these
lines) can never accept it — so making that a fatal turns every validator-bearing
skill into one that can never pass predict, and Studio gates run behind a passing
predict. The flight continues instead, and the downgrade is recorded on the phase.

Golden (P0) and manual/Copilot override (P1) outputs stay strict: those are real
recorded / authored outputs, so a validator rejecting them is a true signal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import graph_agent
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.runtime.state_mapper import StateMapper

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: predict-stub-validator
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [answer]
    properties:
      answer: {type: string}
phases:
  - main
---
<phase depends_on="input" output>main</phase>
"""

_SKILL_MD = """---
llm_role: analyst
validator: true
io:
  inputs:
    type: object
    required: [topic]
    properties:
      topic: {type: string}
  outputs:
    type: object
    required: [answer]
    properties:
      answer: {type: string}
---
<role>Analyst.</role>
<goal>Produce `answer` for the topic, then finish the task.</goal>
"""

_ALWAYS_REJECTING_VALIDATOR = '''
def validate(output, state_slice, **kwargs):
    """Semantic check no fabricated stub can satisfy."""
    raise ValueError("answer must quote the source chapter verbatim")
'''


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def validator_skill(tmp_path: Path) -> Path:
    skill = tmp_path / "skill"
    _write(skill / "GRAPH.md", _GRAPH_MD)
    _write(skill / "phases" / "main" / "SKILL.md", _SKILL_MD)
    _write(skill / "phases" / "main" / "validator.py", _ALWAYS_REJECTING_VALIDATOR)
    return skill


def test_predict_with_stub_mock_downgrades_validator_failure_and_records_it(
    validator_skill: Path, tmp_path: Path
) -> None:
    result = graph_agent.predict_skill(
        validator_skill,
        workspace_dir=tmp_path / "ws",
        topic="mirrors",
    )

    downgraded = [
        phase for phase in result.phases if getattr(phase, "validator_downgraded", None)
    ]
    assert downgraded, (
        "predict must record the downgraded validator on the phase, "
        f"phases={[p.model_dump() for p in result.phases]}"
    )
    assert "verbatim" in downgraded[0].validator_downgraded
    assert downgraded[0].phase_name == "main"


def test_predict_with_manual_override_keeps_validator_strict(
    validator_skill: Path, tmp_path: Path
) -> None:
    """P1 manual/Copilot output is authored, not fabricated — a validator that
    rejects it is a true signal and must stay fatal."""
    with pytest.raises(GraphAgentFatalError) as exc_info:
        graph_agent.predict_skill(
            validator_skill,
            workspace_dir=tmp_path / "ws",
            mock_llm={"main": {"answer": "an authored answer"}},
            topic="mirrors",
        )

    assert "validator" in str(exc_info.value)


def _raising_validator(output: dict[str, object], state_slice: dict[str, object], **_kw: object) -> dict[str, object]:
    raise ValueError("answer must quote the source chapter verbatim")


def _mapper_state() -> WorkflowState:
    return WorkflowState(data=BusinessData(), flow=FrameworkState(), messages=[])


def test_validator_failure_stays_fatal_without_the_stub_downgrade() -> None:
    """Regression lock: the downgrade is opt-in per phase. Default (real run)
    semantics are unchanged — an author validator raising is fatal."""
    mapper = StateMapper(
        output_schema={"type": "object", "properties": {"answer": {}}},
        phase_id="main",
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        mapper.wrap_phase_output(
            _mapper_state(),
            {"data": {"answer": "stub"}},
            validator=_raising_validator,
            validator_error_code="[F-v3-agent-validator-failed]",
        )

    assert "validator" in str(exc_info.value)


def test_stub_downgrade_keeps_mock_output_and_reports_the_rejection() -> None:
    """With the downgrade on, the flight continues on the schema-conform mock
    output and the rejection is handed to the reporter (never swallowed)."""
    reported: list[tuple[str, str]] = []
    mapper = StateMapper(
        output_schema={"type": "object", "properties": {"answer": {}}},
        phase_id="main",
        validator_downgrade_hook=lambda phase_id, message: bool(reported.append((phase_id, message)) or True),
    )

    delta = mapper.wrap_phase_output(
        _mapper_state(),
        {"data": {"answer": "stub"}},
        validator=_raising_validator,
        validator_error_code="[F-v3-agent-validator-failed]",
    )

    assert delta["data"]["answer"] == "stub"
    assert reported and reported[0][0] == "main"
    assert "verbatim" in reported[0][1]
