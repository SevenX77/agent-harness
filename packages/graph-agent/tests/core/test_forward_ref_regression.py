"""Regression for SKILL-local Pydantic forward refs in the new schema path."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from graph_agent.core.io_manager import IOManager
from graph_agent.core.loader import SkillLoader
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolRuntime
from langgraph.types import Command


def _state() -> WorkflowState:
    return {"data": BusinessData(), "flow": FrameworkState(), "messages": []}


def _handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="handled",
        name=str(request.tool_call.get("name") or ""),
        tool_call_id=str(request.tool_call.get("id") or ""),
    )


def test_loader_forward_ref_schema_survives_cognitive_flow_validation(
    tmp_path: Path,
) -> None:
    script_dir = tmp_path / "script"
    script_dir.mkdir()
    (script_dir / "models.py").write_text(
        "\n".join([
            "from __future__ import annotations",
            "from typing import Literal",
            "from pydantic import BaseModel, Field",
            "",
            "class ForwardRefResult(BaseModel):",
            "    kind: Literal['A', 'B'] = Field(description='kind')",
            "    title: str = Field(description='title')",
        ]),
        encoding="utf-8",
    )
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        "\n".join([
            "---",
            'schema_version: "2.0"',
            "name: forward-ref-smoke",
            "description: forward ref smoke",
            "type: graph",
            "io:",
            "  inputs: []",
            "  outputs: []",
            "phases:",
            "  - name: draft",
            "    mode: llm",
            "    prompt: Write a structured result.",
            "    output_schema: script.models.ForwardRefResult",
            "---",
        ]),
        encoding="utf-8",
    )

    compiled = SkillLoader().compile_skill(skill_path)
    phase = compiled.nodes[0].phase
    assert phase is not None
    assert phase.output_schema is not None

    middleware = CognitiveFlowMiddleware(
        IOManager([]),
        current_phase_schema=phase.output_schema,
        phase_name=phase.name,
    )
    request = ToolCallRequest(
        tool_call={
            "name": "finish_task",
            "id": "call-1",
            "args": {
                "reasoning": "probe",
                "diagnostics_md": "ok",
                "business_data_md": "## item\n- kind: A\n- title: ok",
            },
        },
        tool=None,
        state=_state(),
        runtime=cast(ToolRuntime, None),
    )

    result = middleware.wrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.goto == END
    finish_result: dict[str, Any] = result.update["flow"].finish_task_result
    assert finish_result["schema_validation"] == "passed"
    assert finish_result["business_data_parsed"] == [{"kind": "A", "title": "ok"}]
