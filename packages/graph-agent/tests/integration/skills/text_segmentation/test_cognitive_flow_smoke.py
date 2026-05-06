"""End-to-end smoke for the Phase 2 A2 v3 切轨 against the live
text-segmentation SKILL's dotted-path Pydantic class.

Mirrors ``tests/skills/event_extraction/test_cognitive_flow_smoke.py``
but exercises ``script.models.Segment`` plus
``validate_segmentation_structure`` (the segment-phase business
validator). Together with the event-extraction smoke this proves the
A2 v3 pipeline works for both production SKILLs that ship dotted-path
Pydantic schemas.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware


def _load(path_from_repo_root: str, module_name: str) -> Any:
    """Load a hyphenated-package SKILL script via importlib + register
    it in ``sys.modules`` so Pydantic forward references (notably
    ``Literal[...]`` declared under ``from __future__ import annotations``)
    can resolve. Without the ``sys.modules`` registration,
    ``Segment.model_validate`` raises ``PydanticUserError: Segment is
    not fully defined``.
    """
    import sys

    repo_root = Path(__file__).resolve().parents[6]
    target = repo_root / path_from_repo_root
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _state() -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": FrameworkState(),
        "messages": [],
    }


def _request(
    *,
    name: str,
    args: dict[str, Any],
    state: WorkflowState | dict[str, Any] | None = None,
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": name, "id": "call-1", "args": args},
        tool=None,
        state=state if state is not None else _state(),
        runtime=None,  # type: ignore[arg-type]
    )


def _handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="handled",
        name=str(request.tool_call.get("name") or ""),
        tool_call_id=str(request.tool_call.get("id") or ""),
    )


_GOOD_SEGMENTS_MD = """
## 1
- index: 1
- type: B
- start_line: 1
- end_line: 10
- content: 测试段落内容 1
- confidence: 0.95

## 2
- index: 2
- type: A
- start_line: 11
- end_line: 20
- content: 测试段落内容 2
- confidence: 0.92
"""


def test_segment_pydantic_class_round_trip_through_cognitive_flow() -> None:
    """SKILL.md ``output_schema: script.models.Segment`` resolves to a
    ``type[BaseModel]`` at load time. After A2 v3, CognitiveFlow must
    parse the live segments markdown, validate via Pydantic directly
    (bypassing SchemaEngine), and let the business validator enforce
    line-number continuity.
    """
    models_module = _load(
        "skills/text-segmentation/script/models.py",
        "_text_segmentation_models_under_test",
    )
    validators_module = _load(
        "skills/text-segmentation/script/validators.py",
        "_text_segmentation_validators_under_test",
    )
    segment_cls: type = models_module.Segment
    validator: Callable[
        [list[dict[str, Any]]], tuple[bool, list[str]]
    ] = validators_module.validate_segmentation_structure

    middleware = CognitiveFlowMiddleware(
        IOManager(
            [IODef(source_field="business_data_parsed", target_field="segments")]
        ),
        current_phase_schema=segment_cls,
        business_validator=validator,
        phase_name="segment",
    )
    request = _request(
        name="finish_task",
        args={
            "reasoning": "segmented",
            "diagnostics_md": "ok",
            "business_data_md": _GOOD_SEGMENTS_MD,
        },
    )

    result = middleware.wrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.goto == END
    new_data = result.update["data"]
    assert isinstance(new_data, BusinessData)
    segments = new_data["segments"]
    assert len(segments) == 2
    assert [s["index"] for s in segments] == [1, 2]
    assert [s["type"] for s in segments] == ["B", "A"]


def test_segment_business_validator_catches_line_gap() -> None:
    """``validate_segmentation_structure`` enforces continuous line
    coverage. A gap between segments must surface as a [Business]
    diagnostic on the finish_task rejection — proves business validator
    dispatch fires after the Pydantic schema check passes.
    """
    models_module = _load(
        "skills/text-segmentation/script/models.py",
        "_text_segmentation_models_gap_smoke",
    )
    validators_module = _load(
        "skills/text-segmentation/script/validators.py",
        "_text_segmentation_validators_gap_smoke",
    )
    segment_cls: type = models_module.Segment
    validator: Callable[
        [list[dict[str, Any]]], tuple[bool, list[str]]
    ] = validators_module.validate_segmentation_structure

    gappy_md = """
## 1
- index: 1
- type: B
- start_line: 1
- end_line: 10
- content: 第一段内容
- confidence: 0.95

## 2
- index: 2
- type: B
- start_line: 20
- end_line: 30
- content: 第二段内容（11-19 行被吃掉）
- confidence: 0.95
"""

    middleware = CognitiveFlowMiddleware(
        IOManager([]),
        current_phase_schema=segment_cls,
        business_validator=validator,
        phase_name="segment",
    )
    request = _request(
        name="finish_task",
        args={"business_data_md": gappy_md},
    )

    result = middleware.wrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.goto == "model"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    text = str(message.content)
    assert "[Business]" in text
    assert "Gap" in text
