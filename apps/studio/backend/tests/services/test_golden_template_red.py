"""N4 atom #33: schema -> empty golden template + first-class manual golden write.

Create-path B (manual): for an agent node without golden, generate a schema-valid
empty template from the node's io.outputs (via the engine's generate_heuristic_stub),
let the author fill it, then write it as a *manual* golden keyed by node_id — NOT
through the sealed-run promote path (manual golden has no source run).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from app.models.golden import GoldenBaselinePlan, GoldenTemplate, SetManualGoldenReq
from app.services.golden_diff import (
    list_golden_baselines_for_skill,
    plan_manual_golden_for_node,
    set_manual_golden_for_node,
)
from app.services.golden_template import generate_golden_template
from app.services.skills import resolve_skill_dir

if TYPE_CHECKING:
    from pathlib import Path

AGENT_SKILL = "agent-golden-skill"


@pytest.fixture
def agent_skill(studio_roots: tuple[Path, Path]) -> str:
    """Register a skill whose only output-producing node is an Agent (mode: agent)."""
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / AGENT_SKILL
    (skill_dir / "phases" / "segment").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: agent-golden-skill
description: Agent node with an output schema for template generation
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
    additionalProperties: false
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
    additionalProperties: false
phases:
  - segment
---
<phase depends_on="input" output>segment</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "segment" / "SKILL.md").write_text(
        """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
  outputs:
    type: object
    required: [segments, headline]
    properties:
      segments:
        type: array
        items:
          type: object
      headline:
        type: string
tools: []
max_iterations: 5
---
<role>
You are a narrative segmentation editor.
</role>

<goal>
Segment chapter_content into structured segments.
</goal>

<step id="S1" name="segment">
Produce the segments.
</step>
""",
        encoding="utf-8",
    )
    return AGENT_SKILL


def test_generate_golden_template_builds_schema_valid_stub(agent_skill: str) -> None:
    """The template follows the agent node's io.outputs schema (segments[], headline)."""
    template = generate_golden_template(agent_skill, "segment")

    assert isinstance(template, GoldenTemplate)
    assert template.skill_id == agent_skill
    assert template.node_id == "segment"
    # output_schema is the node's output JSON schema (wire key 'schema')
    assert template.output_schema["type"] == "object"
    assert set(template.output_schema["properties"].keys()) == {"segments", "headline"}
    # The serialized form uses the 'schema' alias as the wire key (extra='forbid').
    dumped = template.model_dump(by_alias=True)
    assert "schema" in dumped
    assert "output_schema" not in dumped
    # template is a structure-valid empty stub matching that schema
    assert set(template.template.keys()) == {"segments", "headline"}
    assert template.template["segments"] == []
    assert isinstance(template.template["headline"], str)


def test_generate_golden_template_rejects_unknown_node(agent_skill: str) -> None:
    """A node id that is not an agent node in the skill cannot yield a template."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        generate_golden_template(agent_skill, "ghost-node")

    assert exc_info.value.status_code == 422


def test_set_manual_golden_writes_node_keyed_baseline_without_run(agent_skill: str) -> None:
    """Manual golden persists a node-keyed baseline with no source run id."""
    expected = {"segments": [{"start": 0}], "headline": "Intro"}

    baseline = set_manual_golden_for_node(
        agent_skill,
        SetManualGoldenReq(node_id="segment", expected_output=expected),
    )

    assert baseline.source_run_id is None
    case_node_ids = [case.node_id for case in baseline.cases]
    assert case_node_ids == ["segment"]

    # The written baseline.json is keyed by node_id, and the case file holds the author value.
    golden_dir = resolve_skill_dir(agent_skill) / ".workspace" / "golden" / "segment"
    assert (golden_dir / "baseline.json").exists()
    case_payload: dict[str, Any] = json.loads(
        (golden_dir / "cases" / "segment.json").read_text(encoding="utf-8")
    )
    assert case_payload["node_id"] == "segment"
    assert case_payload["expected_output"] == expected


def test_set_manual_golden_flips_node_to_has_golden(agent_skill: str) -> None:
    """After a manual write, the listing projects the node into a baseline's cases."""
    set_manual_golden_for_node(
        agent_skill,
        SetManualGoldenReq(node_id="segment", expected_output={"segments": [], "headline": "x"}),
    )

    baselines = list_golden_baselines_for_skill(agent_skill)
    node_ids = {case.node_id for baseline in baselines for case in baseline.cases}
    assert "segment" in node_ids


def test_set_manual_golden_does_not_use_run_snapshot_path(
    agent_skill: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual write must not touch the sealed-run snapshot / promote-guard path."""
    import app.services.golden_diff as golden_diff_module

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("manual golden must not read a sealed-run snapshot")

    monkeypatch.setattr(golden_diff_module, "read_run_result_snapshot_for_golden", _boom)
    monkeypatch.setattr(golden_diff_module, "assert_trace_can_be_promoted_to_golden", _boom)

    baseline = set_manual_golden_for_node(
        agent_skill,
        SetManualGoldenReq(node_id="segment", expected_output={"segments": [], "headline": "x"}),
    )
    assert baseline.cases[0].node_id == "segment"


def test_plan_manual_golden_emits_baseline_report_and_case_files(agent_skill: str) -> None:
    """The manual plan covers exactly baseline.json + report.json + cases/{node}.json.

    Parity with the promote `/golden/plan` plan: the native-fs writer iterates these
    files. The plan must NOT persist anything itself (plan-only).
    """
    expected = {"segments": [{"start": 0}], "headline": "Intro"}

    plan = plan_manual_golden_for_node(agent_skill, "segment", expected)

    assert isinstance(plan, GoldenBaselinePlan)
    file_paths = [f.path for f in plan.files]
    assert file_paths == [
        ".workspace/golden/segment/baseline.json",
        ".workspace/golden/segment/report.json",
        ".workspace/golden/segment/cases/segment.json",
    ]
    # The case file content carries the author-defined expected output.
    case_file = next(f for f in plan.files if f.path.endswith("/cases/segment.json"))
    assert json.loads(case_file.content)["expected_output"] == expected
    assert plan.baseline.source_run_id is None
    assert [case.node_id for case in plan.baseline.cases] == ["segment"]

    # Plan-only: nothing is written to disk by planning.
    golden_dir = resolve_skill_dir(agent_skill) / ".workspace" / "golden" / "segment"
    assert not golden_dir.exists()


def _strip_clock(payload: object) -> object:
    """Drop the wall-clock ``created_at`` so two independent plan builds compare equal."""
    if isinstance(payload, dict):
        return {key: value for key, value in payload.items() if key != "created_at"}
    return payload


def test_set_manual_golden_writes_exactly_the_plan_files(agent_skill: str) -> None:
    """The disk write is single-sourced from the plan: same paths + same content shape.

    This is the contract the browser-fallback path relies on (set = plan + write) and
    that the Tauri path mirrors (plan + native writeWorkspaceFile per file). The plan
    here is built independently from the write, so the only field that can differ is the
    wall-clock ``created_at`` in report.json; everything else must match byte-for-byte.
    """
    expected = {"segments": [{"start": 0}], "headline": "Intro"}

    plan = plan_manual_golden_for_node(agent_skill, "segment", expected)
    set_manual_golden_for_node(
        agent_skill,
        SetManualGoldenReq(node_id="segment", expected_output=expected),
    )

    golden_dir = resolve_skill_dir(agent_skill) / ".workspace" / "golden" / "segment"
    written_paths = [f.path for f in plan.files]
    for plan_file in plan.files:
        relative = plan_file.path.removeprefix(".workspace/golden/segment/")
        on_disk = (golden_dir / relative).read_text(encoding="utf-8")
        assert _strip_clock(json.loads(on_disk)) == _strip_clock(json.loads(plan_file.content)), (
            plan_file.path
        )
    # The write touched exactly the plan's file set — no extra, no missing.
    assert written_paths == [
        ".workspace/golden/segment/baseline.json",
        ".workspace/golden/segment/report.json",
        ".workspace/golden/segment/cases/segment.json",
    ]


def test_plan_manual_golden_does_not_use_run_snapshot_path(
    agent_skill: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual plan must not touch the sealed-run snapshot / promote-guard path."""
    import app.services.golden_diff as golden_diff_module

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("manual golden plan must not read a sealed-run snapshot")

    monkeypatch.setattr(golden_diff_module, "read_run_result_snapshot_for_golden", _boom)
    monkeypatch.setattr(golden_diff_module, "assert_trace_can_be_promoted_to_golden", _boom)

    plan = plan_manual_golden_for_node(agent_skill, "segment", {"segments": [], "headline": "x"})
    assert plan.baseline.cases[0].node_id == "segment"
