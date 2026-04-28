"""Tests for finish_task marker and ValidationMiddleware."""

from __future__ import annotations

import logging
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from graph_agent.cognitive.finish import SELFCHECK_NUDGE, finish_task
from graph_agent.cognitive.middlewares import ValidationMiddleware


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

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert (
            payload["reasoning"]  # type: ignore[index]
            == "Reviewed all required work and completed the phase."
        )
        assert payload["diagnostics_md"] == ""  # type: ignore[index]
        assert payload["business_data_md"] == ""  # type: ignore[index]
        assert payload["schema_validation"] == "skipped"  # type: ignore[index]

    def test_finish_preserves_validation_middleware_payload(self) -> None:
        ctx = {
            "_finish_task_result": {
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

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
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

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["business_data_md"] == VALID_BUSINESS_MD.strip()  # type: ignore[index]
        assert payload["schema_validation"] == "skipped"  # type: ignore[index]

    def test_v2_logs_validation_summary(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        ctx = {"output_schema_path": _schema_path()}

        finish_task(ctx, diagnostics_md="diag", business_data_md=VALID_BUSINESS_MD)

        assert "finish_task: accepted completion marker" in caplog.text
        assert "business_data_len=" in caplog.text


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
        assert seen_payloads == [
            [{"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}]
        ]
        assert ctx["_finish_task_result"] == {
            "business_data_parsed": [
                {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
            ],
            "schema_validation": "passed",
        }

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
