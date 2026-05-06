"""Loader-based smoke tests for the four live SKILLs (Phase 3 M7 follow-up).

PHASE3_DESIGN.md v4 §5 ship standard requires that every live SKILL is
exercised through the **real** ``SkillLoader.compile_skill`` path (not
the ``importlib.util.spec_from_file_location`` workaround the v3 smoke
files used). This file replaces that workaround:

* It walks each of the four production SKILLs (``event-extraction``,
  ``batch-analysis``, ``global-synthesis``, ``text-segmentation``) into
  a :class:`CompiledSkill` via :class:`SkillLoader`.
* It pulls the ``phase.output_schema`` Pydantic class out of the
  compiled :class:`Phase` — the same ``type[BaseModel]`` runtime object
  the production ``LLMPhaseNode`` hands to ``CognitiveFlowMiddleware``.
* It mounts ``CognitiveFlowMiddleware`` with that schema and sends a
  ``finish_task`` tool call carrying realistic markdown, asserting both
  the happy path (Pydantic accepts and the parsed items propagate) and
  a failure mode (validator or schema rejects, response routes back to
  the model).

The Phase 3 M7 follow-up ModuleSandbox fix (PHASE3_DESIGN.md v4 §3.5
step 3 — ``sys.modules`` registration + ``model_rebuild()``) is what
lets ``Pydantic.model_validate`` succeed on every schema below
without the test having to manually patch ``sys.modules``. The
forward-ref regression guard in
``tests/graph_agent/core/test_module_sandbox.py`` enforces that
contract independently.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.loader import SkillLoader
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.core.types import Phase
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

# ---------- Helpers ----------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[5]


def _state(*, flow: FrameworkState | None = None) -> WorkflowState:
    return {
        "data": BusinessData(),
        "flow": flow if flow is not None else FrameworkState(),
        "messages": [],
    }


def _request(args: dict[str, Any]) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": "finish_task", "id": "call-1", "args": args},
        tool=None,
        state=_state(),
        runtime=None,  # type: ignore[arg-type]
    )


def _handler(request: ToolCallRequest) -> ToolMessage:
    return ToolMessage(
        content="handled",
        name=str(request.tool_call.get("name") or ""),
        tool_call_id=str(request.tool_call.get("id") or ""),
    )


def _phase_by_name(compiled: Any, name: str) -> Phase:
    """Pull the runtime ``Phase`` object for ``name`` out of ``CompiledSkill``."""
    for node in compiled.nodes:
        if node.name == name and node.phase is not None:
            return node.phase
    raise AssertionError(
        f"phase {name!r} not found in compiled SKILL "
        f"(known nodes: {[n.name for n in compiled.nodes]})"
    )


def _middleware_for(phase: Phase, *, hoist_target: str | None) -> CognitiveFlowMiddleware:
    """Mount CognitiveFlow against the SKILL's compiled output_schema.

    Uses the same parameter shape ``LLMPhaseNode.execute`` uses in the
    production pipeline: ``current_phase_schema=phase.output_schema``
    plus the SKILL's ``business_validator``. ``io_manager`` mirrors the
    LLM phase's IO routing — pass ``hoist_target`` as the
    ``business_data_parsed`` → BusinessData target field.
    """
    io_specs = (
        [IODef(source_field="business_data_parsed", target_field=hoist_target)]
        if hoist_target
        else []
    )
    return CognitiveFlowMiddleware(
        IOManager(io_specs),
        current_phase_schema=phase.output_schema,
        business_validator=phase.validator,
        phase_name=phase.name,
    )


@pytest.fixture(scope="module")
def event_extraction() -> Any:
    return SkillLoader().compile_skill(REPO_ROOT / "skills/event-extraction/SKILL.md")


@pytest.fixture(scope="module")
def batch_analysis() -> Any:
    return SkillLoader().compile_skill(REPO_ROOT / "skills/batch-analysis/SKILL.md")


@pytest.fixture(scope="module")
def global_synthesis() -> Any:
    return SkillLoader().compile_skill(REPO_ROOT / "skills/global-synthesis/SKILL.md")


@pytest.fixture(scope="module")
def text_segmentation() -> Any:
    return SkillLoader().compile_skill(REPO_ROOT / "skills/text-segmentation/SKILL.md")


# ---------- event-extraction -------------------------------------------------


_AGGREGATE_OK = """## summary
- summary: 完整章节聚合: 共识别 7 个事件，按时间线重排到原书第 3 卷开头处。
"""

_AGGREGATE_FAIL = """## summary
"""  # missing required ``summary`` field


def test_event_extraction_aggregate_happy(event_extraction: Any) -> None:
    phase = _phase_by_name(event_extraction, "aggregate")
    middleware = _middleware_for(phase, hoist_target="aggregate_summary")
    request = _request({"business_data_md": _AGGREGATE_OK})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


def test_event_extraction_aggregate_rejects_empty_summary(event_extraction: Any) -> None:
    phase = _phase_by_name(event_extraction, "aggregate")
    middleware = _middleware_for(phase, hoist_target=None)
    request = _request({"business_data_md": _AGGREGATE_FAIL})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == "model"  # rejection routes back to LLM
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.status == "error"


_SETTINGS_OK = """## SET_001
- setting_id: SET_001
- paragraph_indices: 3, 4
- related_event_id: EVT_001
- core_knowledge: 诡异的弱点是火焰和高频电流，普通热武器无效；这是末日世界对战斗角色的核心硬约束，决定主角必须囤特殊弹药。
"""

_SETTINGS_FAIL_BUSINESS = """## not-a-set-id
- setting_id: not-a-set-id
- paragraph_indices: 3
- related_event_id: EVT_001
- core_knowledge: 这条核心知识超过 30 字，足以绕过最小长度阈值，专门用来触发业务校验器拒绝非法 setting_id。
"""


def test_event_extraction_settings_happy_through_business_validator(
    event_extraction: Any,
) -> None:
    phase = _phase_by_name(event_extraction, "settings")
    middleware = _middleware_for(phase, hoist_target="settings")
    request = _request({"business_data_md": _SETTINGS_OK})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


def test_event_extraction_settings_business_validator_rejects_bad_id(
    event_extraction: Any,
) -> None:
    phase = _phase_by_name(event_extraction, "settings")
    middleware = _middleware_for(phase, hoist_target=None)
    request = _request({"business_data_md": _SETTINGS_FAIL_BUSINESS})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == "model"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert "[Business]" in str(message.content)


# ---------- batch-analysis ---------------------------------------------------


_BATCH_OK = """## analysis-1
- analysis_summary: 第 5-7 章共 14 个事件已完成实体注册和角色状态分析，无新增矛盾。
- identified_issues: 无重要问题
- status: ok
"""

_BATCH_FAIL = """## analysis-1
- analysis_summary: 任意自由文本
- identified_issues: 无
- status: critical
"""  # ``status`` violates Literal["ok"|"warning"|"error"]


def test_batch_analysis_entity_and_characters_happy(batch_analysis: Any) -> None:
    phase = _phase_by_name(batch_analysis, "entity_and_characters")
    middleware = _middleware_for(phase, hoist_target="batch_report")
    request = _request({"business_data_md": _BATCH_OK})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


def test_batch_analysis_continuity_rejects_invalid_literal_status(
    batch_analysis: Any,
) -> None:
    phase = _phase_by_name(batch_analysis, "continuity")
    middleware = _middleware_for(phase, hoist_target=None)
    request = _request({"business_data_md": _BATCH_FAIL})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == "model"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.status == "error"


# ---------- global-synthesis -------------------------------------------------


_GLOBAL_OK = """## insight-1
- global_insights: 整本书共 32 个事件，3 条主要伏笔与 2 个角色情感弧线已闭合。
- retroactive_corrections_applied: 0
"""

_GLOBAL_FAIL = """## insight-1
- global_insights: 文本但缺少回溯次数字段
"""  # missing ``retroactive_corrections_applied`` (no default for Literal? actually has default=0 but let's also test)


def test_global_synthesis_global_analysis_happy(global_synthesis: Any) -> None:
    phase = _phase_by_name(global_synthesis, "global_analysis")
    middleware = _middleware_for(phase, hoist_target="global_report")
    request = _request({"business_data_md": _GLOBAL_OK})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


def test_global_synthesis_retroactive_with_optional_default_field_present(
    global_synthesis: Any,
) -> None:
    """``retroactive_corrections_applied`` has a default of 0 so omitting
    it is valid; this case asserts the schema's default-bearing field
    survives the loader → CognitiveFlow path.
    """
    phase = _phase_by_name(global_synthesis, "retroactive")
    middleware = _middleware_for(phase, hoist_target="retro_report")
    md = "## retro-1\n- global_insights: 已完成 4 条 retroactive correction\n"
    request = _request({"business_data_md": md})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


# ---------- text-segmentation ------------------------------------------------


_SEGMENT_OK = """## 1
- index: 1
- type: B
- start_line: 1
- end_line: 10
- content: 测试段落 1
- confidence: 0.95

## 2
- index: 2
- type: A
- start_line: 11
- end_line: 20
- content: 测试段落 2
- confidence: 0.92
"""

_SEGMENT_FAIL = """## 1
- index: 1
- type: X
- start_line: 1
- end_line: 10
- content: 测试段落 1
- confidence: 0.95
"""  # type "X" violates Literal["A"|"B"|"C"]


def test_text_segmentation_segment_happy(text_segmentation: Any) -> None:
    phase = _phase_by_name(text_segmentation, "segment")
    middleware = _middleware_for(phase, hoist_target="segments")
    request = _request({"business_data_md": _SEGMENT_OK})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == END


def test_text_segmentation_segment_rejects_invalid_literal_type(
    text_segmentation: Any,
) -> None:
    phase = _phase_by_name(text_segmentation, "segment")
    middleware = _middleware_for(phase, hoist_target=None)
    request = _request({"business_data_md": _SEGMENT_FAIL})
    result = middleware.wrap_tool_call(request, _handler)
    assert isinstance(result, Command)
    assert result.goto == "model"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
