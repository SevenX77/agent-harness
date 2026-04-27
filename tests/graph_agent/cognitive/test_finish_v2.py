"""Tests for finish_task v2 markdown-to-json validation."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

from graph_agent.cognitive.finish import finish_task


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


class TestFinishTaskV2:
    def test_v1_signature_still_works(self) -> None:
        ctx: dict[str, object] = {}

        result = finish_task(
            ctx,  # type: ignore[arg-type]
            reasoning="Reviewed all required evidence and completed the phase.",
            evidence='["source-a"]',
            execution_summary="done",
            plan_checklist='[{"step":"s1","completed":true,"quality_check":"ok"}]',
            unresolved_issues="none",
        )

        assert result == "PHASE_COMPLETE"
        payload = ctx["_finish_task_result"]
        assert payload["execution_summary"] == "done"  # type: ignore[index]
        assert payload["evidence"] == ["source-a"]  # type: ignore[index]

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

    def test_v2_with_invalid_business_data_md_raises(self) -> None:
        ctx = {"output_schema_path": _schema_path()}
        invalid_md = """## item-1
- title: Scene plan
- score: high
"""

        with pytest.raises(ValueError) as exc:
            finish_task(ctx, business_data_md=invalid_md)

        msg = str(exc.value)
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

    def test_v2_with_unresolvable_schema_path_raises(self) -> None:
        ctx = {"output_schema_path": "does.not.Exist"}

        with pytest.raises(ValueError) as exc:
            finish_task(ctx, business_data_md=VALID_BUSINESS_MD)

        msg = str(exc.value)
        assert "failed to parse business_data_md or load schema does.not.Exist" in msg

    def test_v2_logs_validation_summary(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        ctx = {"output_schema_path": _schema_path()}

        finish_task(ctx, diagnostics_md="diag", business_data_md=VALID_BUSINESS_MD)

        assert "finish_task v2" in caplog.text
        assert "items=1" in caplog.text
        assert _schema_path() in caplog.text
