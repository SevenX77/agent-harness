"""Tests for finish_task marker (Phase 2/3 schema gate via CognitiveFlow)."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import BaseModel, ConfigDict

from graph_agent.cognitive.finish import SELFCHECK_NUDGE, finish_task
from graph_agent.core.exceptions import SkillCompilationError
from graph_agent.core.loader import load_workflow_from_md
from graph_agent.core.manifest import GraphSkillDef
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.validators.validator_required import check_validator_required
from graph_agent.tools.dynamic_schema import (
    DynamicSchemaDef,
    OutputExampleParseError,
    coerce_item_against_dynamic_schema,
    parse_output_example,
)


class BusinessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    score: int
    tags: list[str] = []


VALID_BUSINESS_MD = """## item-1
- title: Scene plan
- score: 3
- tags: scene, plan
"""

VALID_DYNAMIC_EXAMPLE = """<output_example name="Segment">
## segments
- index (int, required): 段落顺序编号
- type (Literal[A,B,C], required): 段落类型
- start_line (int, required): 起始行号
- end_line (int, required): 结束行号
- content (str, required): 剧情概括
- confidence (float, optional, default=1.0): 置信度
</output_example>
"""

VALID_DYNAMIC_MD = """## segments
- index: 1
- type: B
- start_line: 1
- end_line: 5
- content: 收音机播报上沪沦陷消息
- confidence: 0.95
"""

SIMPLE_DYNAMIC_EXAMPLE = """<output_example name="Summary">
## summary
- title (str, required): 标题
- summary (str, required): 摘要
</output_example>
"""


def _schema_path() -> str:
    return f"{BusinessItem.__module__}.{BusinessItem.__name__}"


def _request(args: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": "finish_task", "id": "call-1", "args": args},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


def _handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="PHASE_COMPLETE",
        name="finish_task",
        tool_call_id=request.tool_call["id"],
    )


def _workflow_state() -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(),
        "messages": [],
    }


def test_selfcheck_nudge_uses_finish_task_v2_contract() -> None:
    assert "diagnostics_md" in SELFCHECK_NUDGE
    assert "business_data_md" in SELFCHECK_NUDGE
    assert "execution_summary" not in SELFCHECK_NUDGE
    assert "plan_checklist" not in SELFCHECK_NUDGE
    assert "unresolved_issues" not in SELFCHECK_NUDGE


class TestFinishTaskV2:
    def test_minimal_finish_with_only_reasoning(self) -> None:
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Reviewed all required work and completed the phase.",
        )

        assert result["duplicate"] is False
        payload = result["value"]
        assert payload["reasoning"] == "Reviewed all required work and completed the phase."
        assert payload["diagnostics_md"] == ""
        assert payload["business_data_md"] == ""
        assert payload["schema_validation"] == "skipped"
        assert ctx == {}

    def test_finish_preserves_validation_middleware_payload(self) -> None:
        ctx = {
            "finish_task_result": {
                "schema_validation": "passed",
                "business_data_parsed": [
                    {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
                ],
            }
        }

        result = finish_task(
            ctx,
            diagnostics_md="## 自检\n- ok",
            business_data_md=VALID_BUSINESS_MD,
        )

        assert result["duplicate"] is True
        payload = result["value"]
        assert payload["schema_validation"] == "passed"
        assert payload["diagnostics_md"] == "## 自检\n- ok"
        assert payload["business_data_md"] == VALID_BUSINESS_MD.strip()
        assert payload["business_data_parsed"] == [
            {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
        ]

    def test_v2_without_output_schema_path_falls_back(self) -> None:
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            diagnostics_md="diag",
            business_data_md=VALID_BUSINESS_MD,
        )

        assert result["duplicate"] is False
        payload = result["value"]
        assert payload["business_data_md"] == VALID_BUSINESS_MD.strip()
        assert payload["schema_validation"] == "skipped"
        assert ctx == {}

    def test_v2_logs_validation_summary(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        ctx = {"output_schema_path": _schema_path()}

        finish_task(ctx, diagnostics_md="diag", business_data_md=VALID_BUSINESS_MD)

        assert "finish_task: accepted completion marker" in caplog.text
        assert "business_data_len=" in caplog.text


class TestFinishTaskWiringMVP2T5:
    """T5 wires SchemaEngine + IOManager hooks into ``finish_task``.

    Today the canonical schema gate is ``CognitiveFlowMiddleware`` (Phase 3
    M7 retired the legacy parallel pipeline); these tests pin the optional
    kwargs so a future caller (test harness or MVP-4 ``LLMPhaseNode``)
    can opt into the defense-in-depth path without breaking the existing
    thin-packager contract.
    """

    def test_default_call_remains_thin_packager(self) -> None:
        """Without the optional kwargs, behaviour is the pre-MVP-2 packager."""
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Defense-in-depth disabled by default.",
            diagnostics_md="diag",
            business_data_md="ignored body",
        )

        assert result["value"]["schema_validation"] == "skipped"
        # Both legacy and design.md §4.2 keys are present.
        assert result["finish_task_result"] is result["value"]
        assert result["diagnostics"] == "diag"

    # T5-hotfix: removed the prior ``test_schema_engine_validates_when_wired_failure``
    # — it asserted "failed" against a hand-empty schema (``fields=()``)
    # and relied on Pydantic ``extra='forbid'`` to reject the raw
    # markdown string finish_task was incorrectly handing the engine.
    # That setup let the test stay green even after the underlying
    # markdown parse step was missing, hiding the real bug. The four
    # tests below replace it with real-schema positive + negative
    # coverage that exercises the parse-then-validate pipeline.

    def _build_item_schema(self):
        """Compile a real two-field schema (title: str, count: int) via SchemaEngine."""
        from graph_agent.core.schema_engine import SchemaEngine

        md = (
            '<output_example name="Item">\n'
            "## item\n"
            "- title (str, required): 标题\n"
            "- count (int, required): 计数\n"
            "</output_example>"
        )
        engine = SchemaEngine()
        schema = engine.parse_from_md(md)
        return engine, schema

    def test_real_schema_validates_parsed_md_passes(self) -> None:
        """Happy path: real schema + valid markdown → schema_validation == 'passed'."""
        engine, schema = self._build_item_schema()

        business_md = (
            "## item-1\n"
            "- title: First post\n"
            "- count: 7\n"
        )

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Real schema + valid markdown.",
            diagnostics_md="diag",
            business_data_md=business_md,
            schema_engine=engine,
            compiled_schema=schema,
        )

        assert result["value"]["schema_validation"] == "passed"
        # T5-hotfix: result must carry the parsed dict view, not the
        # raw markdown string. IOManager.resolve_hoist needs structured
        # data to extract source_field values.
        parsed = result["value"]["business_data_parsed"]
        assert isinstance(parsed, list) and len(parsed) == 1
        assert parsed[0] == {"title": "First post", "count": 7}

    def test_real_schema_catches_missing_required_field(self) -> None:
        """Negative path: real schema with a required field absent → 'failed'."""
        engine, schema = self._build_item_schema()

        # ``count`` is required but missing.
        business_md = (
            "## item-1\n"
            "- title: First post\n"
        )

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            business_data_md=business_md,
            schema_engine=engine,
            compiled_schema=schema,
        )

        assert result["value"]["schema_validation"] == "failed"
        errors = result["value"]["schema_validation_errors"]
        assert isinstance(errors, list) and len(errors) >= 1
        # The error must reference the offending field by name —
        # otherwise downstream LLM retry feedback can't fix it.
        assert any("count" in err for err in errors), (
            f"Expected an error mentioning the missing 'count' field; "
            f"got {errors!r}."
        )

    def test_real_schema_catches_type_mismatch(self) -> None:
        """Negative path: schema requires int, markdown supplies non-int → 'failed'."""
        engine, schema = self._build_item_schema()

        business_md = (
            "## item-1\n"
            "- title: First post\n"
            "- count: not-a-number\n"
        )

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            business_data_md=business_md,
            schema_engine=engine,
            compiled_schema=schema,
        )

        assert result["value"]["schema_validation"] == "failed"
        errors = result["value"]["schema_validation_errors"]
        assert isinstance(errors, list) and len(errors) >= 1

    def test_finish_task_result_carries_parsed_dicts_not_raw_md(self) -> None:
        """Regression: finish_task_result must expose structured data.

        Prior to T5-hotfix the result carried the raw markdown string
        in ``business_data_md`` and *no* parsed view, so
        ``IOManager.resolve_hoist`` couldn't read field values out. We
        pin the parsed-view contract here to prevent re-regression.
        """
        engine, schema = self._build_item_schema()

        business_md = (
            "## item-1\n"
            "- title: alpha\n"
            "- count: 1\n"
            "## item-2\n"
            "- title: beta\n"
            "- count: 2\n"
        )

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            business_data_md=business_md,
            schema_engine=engine,
            compiled_schema=schema,
        )

        parsed = result["value"]["business_data_parsed"]
        assert parsed == [
            {"title": "alpha", "count": 1},
            {"title": "beta", "count": 2},
        ]
        # The legacy raw-markdown view stays available for callers that
        # need the original text (e.g. retry feedback templates).
        assert result["value"]["business_data_md"] == business_md.strip()

    def test_schema_engine_kwargs_optional_independently(self) -> None:
        """Passing only one of (schema_engine, compiled_schema) keeps fallback."""
        from graph_agent.core.schema_engine import SchemaEngine

        engine = SchemaEngine()
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            business_data_md="some body",
            schema_engine=engine,
            compiled_schema=None,
        )

        assert result["value"]["schema_validation"] == "skipped"

    def test_io_manager_kwarg_records_manifest(self) -> None:
        """``io_manager`` kwarg records the declared output count, doesn't hoist.

        Actual hoisting stays in ``phase_executor`` per design §4.3 — this
        test pins that ``finish_task`` only records the spec inventory.
        """
        from graph_agent.core.io_manager import IODef, IOManager

        io_manager = IOManager(
            [
                IODef(source_field="segments", target_field="segments"),
                IODef(source_field="meta", target_field="meta"),
            ]
        )

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            business_data_md="anything",
            io_manager=io_manager,
        )

        assert result["value"]["io_manifest"] == {"output_count": 2}

    def test_design_md_4_2_return_shape(self) -> None:
        """Return shape carries both legacy ``value`` keys and §4.2 keys."""
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Shape lock-in.",
            diagnostics_md="my diagnostics",
            business_data_md="md body",
        )

        # Legacy keys (read by phase_executor._finish_task_tool).
        assert "value" in result
        assert "duplicate" in result
        # design.md §4.2 keys (read by future MVP-3+ adopters).
        assert "finish_task_result" in result
        assert "diagnostics" in result
        assert result["diagnostics"] == "my diagnostics"


class TestSchemaByExample:
    def test_parse_output_example_strict_schema(self) -> None:
        schema = parse_output_example(VALID_DYNAMIC_EXAMPLE)

        assert schema.name == "Segment"
        assert schema.item_header == "segments"
        assert [field.name for field in schema.fields] == [
            "index",
            "type",
            "start_line",
            "end_line",
            "content",
            "confidence",
        ]
        assert schema.fields[1].enum_values == ["A", "B", "C"]

        coerced, errors = coerce_item_against_dynamic_schema(
            {
                "index": "2",
                "type": "A",
                "start_line": "6",
                "end_line": "9",
                "content": "诡异爆发背景设定",
            },
            schema,
        )

        assert errors == []
        assert coerced == {
            "index": 2,
            "type": "A",
            "start_line": 6,
            "end_line": 9,
            "content": "诡异爆发背景设定",
            "confidence": 1.0,
        }

    def test_parse_output_example_rejects_bad_type_spelling(self) -> None:
        bad_example = VALID_DYNAMIC_EXAMPLE.replace(
            "- index (int, required):",
            "- index (Int, required):",
        )

        with pytest.raises(OutputExampleParseError, match="Unsupported type 'Int'"):
            parse_output_example(bad_example)

    def test_loader_threads_dynamic_schema_and_output_format(
        self,
        tmp_path: Path,
    ) -> None:
        skill = _write_schema_by_example_skill(tmp_path, VALID_DYNAMIC_EXAMPLE)

        harness = load_workflow_from_md(skill)

        phase = harness.phases[0]
        assert isinstance(phase.output_schema, DynamicSchemaDef)
        assert phase.output_schema_path is None
        assert "<output_format>" in (phase.system_prompt or "")
        assert "## segments" in (phase.system_prompt or "")
        assert "- index: <值>" in (phase.system_prompt or "")

    def test_loader_rejects_invalid_output_example_as_fatal(
        self,
        tmp_path: Path,
    ) -> None:
        bad_example = VALID_DYNAMIC_EXAMPLE.replace(
            "- index (int, required):",
            "- index (Int, required):",
        )
        skill = _write_schema_by_example_skill(tmp_path, bad_example)

        with pytest.raises(SkillCompilationError, match="F-output-example-invalid"):
            load_workflow_from_md(skill)


class TestValidatorRequiredRule:
    def test_complex_schema_with_validator_has_no_issue(self) -> None:
        manifest = _graph_manifest(
            [
                _validator_rule_phase(
                    output_example=VALID_DYNAMIC_EXAMPLE,
                    validator="script.validators.validate_segments",
                )
            ]
        )

        assert check_validator_required(manifest) == []

    def test_simple_schema_without_validator_warns(self) -> None:
        manifest = _graph_manifest([_validator_rule_phase(output_example=SIMPLE_DYNAMIC_EXAMPLE)])

        issues = check_validator_required(manifest)

        assert len(issues) == 1
        assert issues[0].rule_id == "W-VALIDATOR-MISSING"
        assert issues[0].severity == "WARNING"

    def test_simple_schema_with_validator_optional_silences_warning(self) -> None:
        manifest = _graph_manifest(
            [
                _validator_rule_phase(
                    output_example=SIMPLE_DYNAMIC_EXAMPLE,
                    validator_optional=True,
                )
            ]
        )

        assert check_validator_required(manifest) == []

    def test_complex_schema_without_validator_is_fatal(self) -> None:
        manifest = _graph_manifest([_validator_rule_phase(output_example=VALID_DYNAMIC_EXAMPLE)])

        issues = check_validator_required(manifest)

        assert len(issues) == 1
        assert issues[0].rule_id == "F-VALIDATOR-MISSING-FOR-COMPLEX-SCHEMA"
        assert issues[0].severity == "FATAL"
        assert "start_line <= end_line" in issues[0].message

    def test_phase_without_output_schema_is_exempt(self) -> None:
        manifest = _graph_manifest([_validator_rule_phase(output_example=None)])

        assert check_validator_required(manifest) == []


def _graph_manifest(phases: list[dict[str, Any]]) -> GraphSkillDef:
    return GraphSkillDef.model_validate(
        {
            "schema_version": "2.0",
            "type": "graph",
            "name": "validator-required-test",
            "description": "validator-required-test",
            "io": {"inputs": [], "outputs": []},
            "phases": phases,
        }
    )


def _validator_rule_phase(
    *,
    output_example: str | None,
    validator: str | None = None,
    validator_optional: bool = False,
) -> dict[str, Any]:
    phase: dict[str, Any] = {
        "name": "segment",
        "mode": "llm",
        "prompt": "Do the work.",
    }
    if output_example is not None:
        phase["output_example"] = output_example
    if validator is not None:
        phase["validator"] = validator
    if validator_optional:
        phase["validator_optional"] = True
    return phase


def _write_schema_by_example_skill(tmp_path: Path, output_example: str) -> Path:
    skill = tmp_path / "SKILL.md"
    indented_example = textwrap.indent(output_example.strip(), "      ")
    skill.write_text(
        f"""---
schema_version: "2.0"
name: schema-by-example-test
description: schema-by-example-test
type: graph
io:
  inputs: []
  outputs: []
phases:
  - name: segment
    mode: llm
    llm_role: analyst
    validator_optional: true
    output_example: |
{indented_example}
    prompt: |
      Call finish_task with business_data_md.
---
""",
        encoding="utf-8",
    )
    return skill
