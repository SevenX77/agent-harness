from __future__ import annotations

from typing import Any

from graph_agent.cognitive.finish_task import FinishTaskInput, build_finish_task_tool
from graph_agent.cognitive.md2json import Md2JsonResult


def _md2json_stub(markdown: str, output_schema: dict[str, Any] | None) -> Md2JsonResult:
    del output_schema
    return Md2JsonResult(
        data={"answer": markdown.strip()},
        validation_errors=[],
        repaired=False,
    )


def test_finish_task_tool_schema_matches_cognitive_flow_raw_args_contract() -> None:
    expected_fields = {"reasoning", "diagnostics_md", "business_data_md"}

    assert set(FinishTaskInput.model_fields) >= expected_fields
    assert "markdown" not in FinishTaskInput.model_fields

    tool = build_finish_task_tool(None, _md2json_stub)
    assert set(tool.args_schema.model_fields) >= expected_fields
    assert "markdown" not in tool.args_schema.model_fields
