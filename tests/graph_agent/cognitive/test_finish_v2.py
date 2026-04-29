"""Tests for finish_task marker and ValidationMiddleware."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from graph_agent.cognitive.finish import SELFCHECK_NUDGE, finish_task
from graph_agent.cognitive.middlewares import ValidationMiddleware
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

    Today the canonical schema gate is ``ValidationMiddleware``; these
    tests pin the optional kwargs so a future caller (test harness or
    MVP-4 ``LLMPhaseNode``) can opt into the defense-in-depth path
    without breaking the existing thin-packager contract.
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

    def test_schema_engine_validates_when_wired_failure(self) -> None:
        """When ``schema_engine`` + ``compiled_schema`` are passed, run validation.

        We pin the failure path because the SchemaEngine-generated
        Pydantic model carries ``extra='forbid'`` and finish_task feeds
        in ``{"business_data_md": ...}`` — an unknown key from the empty
        schema's perspective. Surfacing the rejection as
        ``schema_validation='failed'`` plus a populated
        ``schema_validation_errors`` list is the wiring contract; the
        canonical authoring path keeps the validation in
        ``ValidationMiddleware`` upstream.
        """
        from graph_agent.core.schema_engine import SchemaEngine, SchemaObject

        engine = SchemaEngine()
        schema = SchemaObject(fields=(), required_fields=frozenset())

        ctx: dict[str, object] = {}
        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Validating via wired SchemaEngine.",
            diagnostics_md="diag",
            business_data_md="## item\n- name: ok",
            schema_engine=engine,
            compiled_schema=schema,
        )

        assert result["value"]["schema_validation"] == "failed"
        errors = result["value"]["schema_validation_errors"]
        assert isinstance(errors, list) and len(errors) >= 1

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


class TestValidationMiddleware:
    def test_rejects_empty_schema_submission(self) -> None:
        ctx: dict[str, Any] = {}
        middleware = ValidationMiddleware(output_schema=BusinessItem, ctx=ctx)

        def handler(_request: ToolCallRequest) -> ToolMessage:
            raise AssertionError("finish_task handler should not run")

        result = middleware.wrap_tool_call(_request({"business_data_md": ""}), handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        assert "提交已被系统驳回" in str(message.content)
        assert "business_data_md 是空" in str(message.content)
        assert "_finish_task_result" not in ctx

    def test_invalid_json_args_returns_llm_feedback(self) -> None:
        ctx: dict[str, Any] = {}
        middleware = ValidationMiddleware(
            output_schema=BusinessItem,
            ctx=ctx,
            phase_name="finish_phase",
        )
        request = ToolCallRequest(
            tool_call={"name": "finish_task", "id": "call-1", "args": "{bad json"},
            tool=None,
            state={},
            runtime=None,  # type: ignore[arg-type]
        )

        def handler(_request: ToolCallRequest) -> ToolMessage:
            raise AssertionError("finish_task handler should not run")

        result = middleware.wrap_tool_call(request, handler)

        assert isinstance(result, Command)
        assert result.goto == "model"
        message = result.update["messages"][0]
        assert isinstance(message, ToolMessage)
        assert message.status == "error"
        assert message.name == "finish_task"
        assert message.tool_call_id == "call-1"
        assert "JSON parse failed" in str(message.content)
        assert "Please retry with valid JSON" in str(message.content)
        assert "_finish_task_result" not in ctx

    def test_accepts_valid_schema_submission(self) -> None:
        ctx: dict[str, Any] = {}
        seen_payloads: list[Any] = []

        def business_validator(payload: list[dict[str, Any]]) -> tuple[bool, list[str]]:
            seen_payloads.append(payload)
            return True, []

        middleware = ValidationMiddleware(
            output_schema=BusinessItem,
            business_validator=business_validator,
            ctx=ctx,
        )

        result = middleware.wrap_tool_call(
            _request({"business_data_md": VALID_BUSINESS_MD}),
            _handler,
        )

        assert isinstance(result, ToolMessage)
        assert seen_payloads == [[{"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}]]
        assert ctx["_finish_task_result"] == {
            "business_data_parsed": [
                {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
            ],
            "schema_validation": "passed",
        }

    def test_accepts_valid_schema_submission_updates_workflow_state(self) -> None:
        ctx: dict[str, Any] = {}
        state = _workflow_state()
        middleware = ValidationMiddleware(
            output_schema=BusinessItem,
            ctx=ctx,
            workflow_state=state,
        )

        result = middleware.wrap_tool_call(
            _request({"business_data_md": VALID_BUSINESS_MD}),
            _handler,
        )

        assert isinstance(result, ToolMessage)
        assert middleware.workflow_state is not None
        assert middleware.workflow_state is not state
        assert middleware.workflow_state["flow"].finish_task_result == {
            "business_data_parsed": [
                {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
            ],
            "schema_validation": "passed",
        }
        assert state["flow"].finish_task_result is None

    def test_rejects_pydantic_errors(self) -> None:
        ctx: dict[str, Any] = {}
        middleware = ValidationMiddleware(output_schema=BusinessItem, ctx=ctx)
        invalid_md = """## item-1
- title: Scene plan
- score: high
"""

        def handler(_request: ToolCallRequest) -> ToolMessage:
            raise AssertionError("finish_task handler should not run")

        result = middleware.wrap_tool_call(
            _request({"business_data_md": invalid_md}),
            handler,
        )

        assert isinstance(result, Command)
        content = str(result.update["messages"][0].content)
        assert "[Pydantic] item-1" in content
        assert "score" in content
        assert "_finish_task_result" not in ctx

    def test_rejects_unresolvable_schema_path(self) -> None:
        ctx: dict[str, Any] = {}
        middleware = ValidationMiddleware(output_schema_path="does.not.Exist", ctx=ctx)

        result = middleware.wrap_tool_call(
            _request({"business_data_md": VALID_BUSINESS_MD}),
            _handler,
        )

        assert isinstance(result, Command)
        assert "无法加载 output_schema 'does.not.Exist'" in str(
            result.update["messages"][0].content
        )

    def test_rejects_business_validator_errors(self) -> None:
        ctx: dict[str, Any] = {}

        def business_validator(_payload: list[dict[str, Any]]) -> tuple[bool, list[str]]:
            return False, ["segment boundary gap"]

        middleware = ValidationMiddleware(
            output_schema=BusinessItem,
            business_validator=business_validator,
            ctx=ctx,
        )

        result = middleware.wrap_tool_call(
            _request({"business_data_md": VALID_BUSINESS_MD}),
            _handler,
        )

        assert isinstance(result, Command)
        assert "[Business] segment boundary gap" in str(result.update["messages"][0].content)
        assert "_finish_task_result" not in ctx

    def test_runs_context_validator_without_schema(self) -> None:
        ctx: dict[str, Any] = {"ready": False}

        def business_validator(payload: dict[str, Any]) -> tuple[bool, list[str]]:
            return bool(payload.get("ready")), ["context not ready"]

        middleware = ValidationMiddleware(business_validator=business_validator, ctx=ctx)

        rejected = middleware.wrap_tool_call(_request({}), _handler)
        assert isinstance(rejected, Command)
        assert "[Business] context not ready" in str(rejected.update["messages"][0].content)

        ctx["ready"] = True
        accepted = middleware.wrap_tool_call(_request({}), _handler)
        assert isinstance(accepted, ToolMessage)

    def test_accepts_dynamic_schema_submission(self) -> None:
        ctx: dict[str, Any] = {}
        seen_payloads: list[Any] = []
        schema = parse_output_example(VALID_DYNAMIC_EXAMPLE)

        def business_validator(payload: list[dict[str, Any]]) -> tuple[bool, list[str]]:
            seen_payloads.append(payload)
            return True, []

        middleware = ValidationMiddleware(
            output_schema=schema,
            business_validator=business_validator,
            ctx=ctx,
        )

        result = middleware.wrap_tool_call(
            _request({"business_data_md": VALID_DYNAMIC_MD}),
            _handler,
        )

        assert isinstance(result, ToolMessage)
        assert seen_payloads == [
            [
                {
                    "index": 1,
                    "type": "B",
                    "start_line": 1,
                    "end_line": 5,
                    "content": "收音机播报上沪沦陷消息",
                    "confidence": 0.95,
                }
            ]
        ]
        assert ctx["_finish_task_result"] == {
            "business_data_parsed": seen_payloads[0],
            "schema_validation": "passed",
            "schema_type": "dynamic",
            "schema_name": "Segment",
        }

    def test_rejects_dynamic_schema_errors(self) -> None:
        ctx: dict[str, Any] = {}
        schema = parse_output_example(VALID_DYNAMIC_EXAMPLE)
        middleware = ValidationMiddleware(output_schema=schema, ctx=ctx)
        invalid_md = """## segments
- index: 1
- type: D
- start_line: 1
- end_line: 5
- extra: no
"""

        result = middleware.wrap_tool_call(
            _request({"business_data_md": invalid_md}),
            _handler,
        )

        assert isinstance(result, Command)
        content = str(result.update["messages"][0].content)
        assert "[DynamicSchema] segments" in content
        assert "not in ['A', 'B', 'C']" in content
        assert "Unknown field 'extra'" in content
        assert "Missing required field 'content'" in content
        assert "_finish_task_result" not in ctx


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
