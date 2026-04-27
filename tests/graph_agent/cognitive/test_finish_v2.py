"""Tests for finish_task v2 markdown-to-json validation."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

import graph_agent.cognitive.finish as finish_mod
from graph_agent.cognitive.finish import SELFCHECK_NUDGE, finish_task


class BusinessItem(BaseModel):
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

    def test_v2_with_valid_business_data_md(self) -> None:
        ctx = {"output_schema_path": _schema_path()}

        result = finish_task(
            ctx,
            diagnostics_md="## 自检\n- ok",
            business_data_md=VALID_BUSINESS_MD,
        )

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["schema_validation"] == "passed"
        assert payload["diagnostics_md"] == "## 自检\n- ok"
        assert payload["business_data_parsed"] == [
            {"title": "Scene plan", "score": 3, "tags": ["scene", "plan"]}
        ]

    def test_v2_with_invalid_business_data_md_writes_ctx_failed(self) -> None:
        ctx = {"output_schema_path": _schema_path()}
        invalid_md = """## item-1
- title: Scene plan
- score: high
"""

        result = finish_task(ctx, business_data_md=invalid_md)

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["schema_validation"] == "failed"
        msg = payload["validation_error_text"]
        assert "business_data_md schema validation failed" in msg
        assert "score" in msg
        assert "语义错误" in msg

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
        assert payload["business_data_parsed"] is None  # type: ignore[index]
        assert payload["schema_validation"] == "skipped: no output_schema declared"  # type: ignore[index]

    def test_v2_with_unresolvable_schema_path_writes_ctx_failed(self) -> None:
        ctx = {"output_schema_path": "does.not.Exist"}

        result = finish_task(ctx, business_data_md=VALID_BUSINESS_MD)

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["schema_validation"] == "failed"
        msg = payload["validation_error_text"]
        assert "failed to parse business_data_md or load schema does.not.Exist" in msg

    def test_schema_validation_error_uses_template_constant(self) -> None:
        ctx = {"output_schema_path": _schema_path()}
        invalid_md = """## item-1
- title: Scene plan
- score: high
"""

        result = finish_task(ctx, business_data_md=invalid_md)

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["schema_validation"] == "failed"
        msg = payload["validation_error_text"]
        assert "business_data_md schema validation failed" in msg
        assert "score" in msg

    def test_parse_error_uses_template_constant(self) -> None:
        ctx = {"output_schema_path": "does.not.Exist"}

        result = finish_task(ctx, business_data_md=VALID_BUSINESS_MD)

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["schema_validation"] == "failed"
        msg = payload["validation_error_text"]
        assert "failed to parse business_data_md or load schema does.not.Exist" in msg

    def test_template_constants_can_be_monkey_patched(self) -> None:
        ctx = {"output_schema_path": _schema_path()}
        invalid_md = """## item-1
- title: Scene plan
- score: high
"""
        original = finish_mod.SCHEMA_VALIDATION_ERROR_TEMPLATE
        try:
            finish_mod.SCHEMA_VALIDATION_ERROR_TEMPLATE = "english override: {exc}"

            result = finish_task(ctx, business_data_md=invalid_md)

            assert result == "PHASE_COMPLETE"
            payload = ctx["_finish_task_result"]
            assert payload["schema_validation"] == "failed"
            assert "english override:" in payload["validation_error_text"]
            assert "score" in payload["validation_error_text"]
        finally:
            finish_mod.SCHEMA_VALIDATION_ERROR_TEMPLATE = original

    def test_v2_logs_validation_summary(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        ctx = {"output_schema_path": _schema_path()}

        finish_task(ctx, diagnostics_md="diag", business_data_md=VALID_BUSINESS_MD)

        assert "finish_task v2" in caplog.text
        assert "items=1" in caplog.text
        assert _schema_path() in caplog.text
