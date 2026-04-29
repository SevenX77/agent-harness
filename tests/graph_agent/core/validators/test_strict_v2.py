"""Tests for strict compile rules v2 (12 WARN-tier rules; Step A).

Covers:
- check_exit_contract (5 rules)
- check_io_schema (3 rules)
- check_io_traceability (3 rules)
- check_pipeline_alignment (1 rule, shallow field-key coverage)
"""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

from graph_agent.core.validators.strict_v2 import (
    _has_exit_contract_marker,
    _is_legacy_data_piping_tool,
    _parse_inline_example,
    check_exit_contract,
    check_io_schema,
    check_io_traceability,
    check_pipeline_alignment,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _llm_phase(
    name: str = "phase1",
    prompt: str = "x" * 250,  # exceed 200-char threshold
    user_prompt_template: str | None = None,
    hoist_to: str | None = None,
    output_example: str | None = None,
    output_schema: str | None = None,
    agent_tools: list[str] | None = None,
    is_router: bool = False,
):
    from graph_agent.core.manifest import LLMPhase
    return LLMPhase(
        mode="llm",
        name=name,
        prompt=prompt,
        user_prompt_template=user_prompt_template,
        hoist_to=hoist_to,
        output_example=output_example,
        output_schema=output_schema,
        agent_tools=agent_tools or [],
        is_router=is_router,
    )


def _logic_phase(name: str, execute_steps: list[str] | None = None):
    from graph_agent.core.manifest import LogicPhase
    return LogicPhase(
        mode="logic",
        name=name,
        execute_steps=execute_steps or ["pkg.module.fn"],
    )


def _graph_skill(
    phases: list,
    inputs: list | None = None,
    outputs: list | None = None,
    context_mapping: dict | None = None,
):
    from graph_agent.core.manifest import GraphSkillDef, IoDeclaration

    return GraphSkillDef(
        schema_version="2.0",
        name="test-skill",
        type="graph",
        description="Test skill",
        phases=phases,
        io=IoDeclaration(
            inputs=inputs or [],
            outputs=outputs or [],
        ),
        context_mapping=context_mapping or {},
    )


# ---------------------------------------------------------------------------
# Helper-fn unit tests
# ---------------------------------------------------------------------------


def test_exit_contract_marker_recognises_v3_pattern() -> None:
    assert _has_exit_contract_marker("## ⚠️ 退出契约（最高优先级）\n本阶段...")
    assert _has_exit_contract_marker("# EXIT CONTRACT\nFinish via finish_task...")
    assert not _has_exit_contract_marker("请调用 finish_task 报告完成。")


def test_legacy_data_piping_tool_detection() -> None:
    assert _is_legacy_data_piping_tool("script.extractor.store_events")
    assert _is_legacy_data_piping_tool("script.extractor.safe_review_store_events")
    assert _is_legacy_data_piping_tool("script.extractor.backup_event_timeline")
    assert _is_legacy_data_piping_tool("script.extractor.finalize_event_timeline")
    assert not _is_legacy_data_piping_tool("script.extractor.parse_events")
    assert not _is_legacy_data_piping_tool("script.extractor.log_ambiguous_events")


def test_parse_inline_example_extracts_field_names() -> None:
    block = """
<output_example name="Segment">
## segments
- index (int, required): seq num
- type (Literal[A,B,C], required): type
- start_line (int, required): line start
</output_example>
"""
    fields = _parse_inline_example(block)
    assert fields == {"index", "type", "start_line"}


def test_parse_inline_example_handles_empty() -> None:
    assert _parse_inline_example("") == set()
    assert _parse_inline_example(None) == set()


# ---------------------------------------------------------------------------
# check_exit_contract
# ---------------------------------------------------------------------------


def test_finish_task_contract_missing_fires_when_no_marker() -> None:
    phase = _llm_phase(prompt="一段长 prompt 没有退出契约块。" + "x" * 300 + "请调用 finish_task。")
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-FINISH-TASK-CONTRACT-MISSING" in rule_ids


def test_finish_task_contract_silent_with_marker() -> None:
    prompt = (
        "## ⚠️ 退出契约（最高优先级）\n"
        "本阶段唯一退出方式是调用 finish_task。\n" + "x" * 250
    )
    phase = _llm_phase(prompt=prompt, hoist_to="result", output_example="<output_example name=\"X\">\n## items\n- f (str, required): foo\n</output_example>")
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-FINISH-TASK-CONTRACT-MISSING" not in rule_ids


def test_output_schema_missing_when_hoisting_fires() -> None:
    phase = _llm_phase(hoist_to="result", output_example=None, output_schema=None, prompt="## ⚠️ 退出契约\n" + "x" * 250)
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-OUTPUT-SCHEMA-MISSING-WHEN-HOISTING" in rule_ids


def test_output_schema_silent_when_pydantic_path_set() -> None:
    """V2 pivot: declaring output_schema (Pydantic dotted path) satisfies the contract."""
    phase = _llm_phase(
        hoist_to="result",
        output_schema="script.models.Foo",
        output_example=None,
        prompt="## ⚠️ 退出契约\n" + "x" * 250,
    )
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-OUTPUT-SCHEMA-MISSING-WHEN-HOISTING" not in rule_ids


def test_llm_phase_no_output_channel_fires_for_dead_end_phase() -> None:
    phase = _llm_phase(
        hoist_to=None,
        output_example=None,
        output_schema=None,
        agent_tools=["script.foo.parse_x"],  # not a legacy store
        prompt="## ⚠️ 退出契约\n" + "x" * 250,
    )
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-LLM-PHASE-NO-OUTPUT-CHANNEL" in rule_ids


def test_llm_phase_no_output_channel_skipped_for_router() -> None:
    phase = _llm_phase(
        hoist_to=None,
        is_router=True,
        agent_tools=[],
        prompt="## ⚠️ 退出契约\n" + "x" * 250,
    )
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-LLM-PHASE-NO-OUTPUT-CHANNEL" not in rule_ids


def test_llm_phase_no_output_channel_silenced_by_legacy_store_tool() -> None:
    phase = _llm_phase(
        hoist_to=None,
        agent_tools=["script.x.store_events"],
        prompt="## ⚠️ 退出契约\n" + "x" * 250,
    )
    skill = _graph_skill(phases=[phase])
    rule_ids = {i.rule_id for i in check_exit_contract(skill)}
    assert "W-LLM-PHASE-NO-OUTPUT-CHANNEL" not in rule_ids


# ---------------------------------------------------------------------------
# check_io_schema
# ---------------------------------------------------------------------------


def test_io_input_no_schema_fires_when_neither_ref_nor_example() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="x", type="str", source="runtime")],
    )
    rule_ids = {i.rule_id for i in check_io_schema(skill)}
    assert "W-IO-INPUT-NO-SCHEMA" in rule_ids


def test_io_input_silent_with_example() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="x", type="str", source="runtime", example="hi", allow_empty=False)],
    )
    rule_ids = {i.rule_id for i in check_io_schema(skill)}
    assert "W-IO-INPUT-NO-SCHEMA" not in rule_ids


def test_io_field_missing_empty_policy_fires() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="x", type="str", source="runtime", example="x")],  # no allow_empty/default/on_empty
    )
    rule_ids = {i.rule_id for i in check_io_schema(skill)}
    assert "W-IO-FIELD-MISSING-EMPTY-POLICY" in rule_ids


# ---------------------------------------------------------------------------
# check_io_traceability
# ---------------------------------------------------------------------------


def test_legacy_data_piping_tool_warning_fires() -> None:
    phase = _llm_phase(
        hoist_to="x",
        output_example="<output_example name=\"X\">\n## items\n- f (str, required): foo\n</output_example>",
        agent_tools=["script.legacy.store_events", "script.legacy.parse_events"],
        prompt="## ⚠️ 退出契约\n" + "x" * 250,
    )
    skill = _graph_skill(phases=[phase])
    rule_ids = [i.rule_id for i in check_io_traceability(skill)]
    assert rule_ids.count("W-LEGACY-DATA-PIPING-TOOL") == 1


def test_input_not_connected_fires_when_no_context_mapping_uses_input() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="orphaned", type="str", source="runtime", example="x", allow_empty=True)],
        context_mapping={"other_var": "{input.something_else}"},
    )
    rule_ids = {i.rule_id for i in check_io_traceability(skill)}
    assert "W-IO-INPUT-NOT-CONNECTED" in rule_ids


def test_input_not_connected_silent_when_referenced() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="x", type="str", source="runtime", example="x", allow_empty=True)],
        context_mapping={"x": "{input.x}"},
    )
    rule_ids = {i.rule_id for i in check_io_traceability(skill)}
    assert "W-IO-INPUT-NOT-CONNECTED" not in rule_ids


# ---------------------------------------------------------------------------
# check_pipeline_alignment (shallow field-key coverage, Gemini-downgraded)
# ---------------------------------------------------------------------------


def test_pipeline_field_coverage_silent_when_no_schema_ref() -> None:
    from graph_agent.core.manifest import IoInput
    skill = _graph_skill(
        phases=[_logic_phase("setup")],
        inputs=[IoInput(name="x", type="str", source="runtime", example="hi", allow_empty=True)],
    )
    issues = check_pipeline_alignment(skill, skill_path="skills/dummy/SKILL.md")
    assert issues == []
