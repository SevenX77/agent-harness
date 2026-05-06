"""End-to-end smoke for the Phase 2 A2 v3 切轨 against the live
event-extraction SKILL's dotted-path Pydantic class.

Per PHASE2_DESIGN.md §6.2, every live SKILL validator path must have a
runtime smoke test. The A1 smoke covered the validator's
``list[dict[str, Any]]`` contract in isolation; this A2 smoke wires
``CognitiveFlowMiddleware`` with the production SKILL's actual Pydantic
class (``Setting`` from ``skills/event-extraction/script/models.py``)
plus the production validator and asserts the markdown-string round
trip + business-validator dispatch all complete on the new pipeline.

Catches the v3 implementation regression where dotted-path SKILLs hit
the ``schema is None`` raise in ``CognitiveFlowMiddleware`` because the
schema dispatch did not accept ``type[BaseModel]``.

The validator script and Pydantic class live under hyphenated
``skills/event-extraction/`` so we load them via
``importlib.util.spec_from_file_location`` — the same pattern as
``test_validators_runtime.py`` and ``test_md_to_json.py``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from graph_agent.core.io_manager import IODef, IOManager
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


def _load(path_from_repo_root: str, module_name: str) -> Any:
    repo_root = Path(__file__).resolve().parents[6]
    target = repo_root / path_from_repo_root
    spec = importlib.util.spec_from_file_location(module_name, target)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(
    *,
    data: BusinessData | None = None,
    flow: FrameworkState | None = None,
) -> WorkflowState:
    return {
        "data": data if data is not None else BusinessData(),
        "flow": flow if flow is not None else FrameworkState(),
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


# md_to_json's flat-list parser splits ``key: a, b, c`` on commas. Lists
# must therefore be emitted without surrounding brackets so the
# elements coerce cleanly to int.
_GOOD_SETTINGS_MD = """
## SET_001
- setting_id: SET_001
- paragraph_indices: 3, 4, 5
- related_event_id: EVT_001
- core_knowledge: 诡异的弱点是火焰与高频电流，普通热武器对其无效。这是末日世界对战斗角色提出的核心硬约束，决定了主角必须囤积特殊弹药。

## SET_002
- setting_id: SET_002
- paragraph_indices: 12, 13
- related_event_id: EVT_004
- core_knowledge: 序列超凡体系分为序列9到序列0，越靠近0越强。觉醒序列必须服用对应针剂，每一层升序都伴随精神风险，是末世修炼的核心规则。
"""


def test_setting_pydantic_class_round_trip_through_cognitive_flow() -> None:
    """SKILL.md ``output_schema: script.models.Setting`` resolves to a
    ``type[BaseModel]`` at load time. After A2 v3, CognitiveFlow must
    accept the Pydantic class directly, parse the LLM markdown, and
    forward the parsed list to the business validator without trip-
    wiring on the legacy ``SchemaObject``-only assumption.
    """
    models_module = _load(
        "skills/event-extraction/script/models.py",
        "_event_extraction_models_under_test",
    )
    validators_module = _load(
        "skills/event-extraction/script/validators.py",
        "_event_extraction_validators_under_test",
    )
    setting_cls: type = models_module.Setting
    validator: Callable[
        [list[dict[str, Any]]], tuple[bool, list[str]]
    ] = validators_module.validate_event_extraction

    middleware = CognitiveFlowMiddleware(
        IOManager(
            [IODef(source_field="business_data_parsed", target_field="settings")]
        ),
        current_phase_schema=setting_cls,
        business_validator=validator,
        phase_name="settings",
    )
    state = _state()
    request = _request(
        name="finish_task",
        args={
            "reasoning": "extracted two settings",
            "diagnostics_md": "ok",
            "business_data_md": _GOOD_SETTINGS_MD,
        },
        state=state,
    )

    result = middleware.wrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.goto == END
    new_data = result.update["data"]
    assert isinstance(new_data, BusinessData)
    settings = new_data["settings"]
    assert len(settings) == 2
    assert {item["setting_id"] for item in settings} == {"SET_001", "SET_002"}
    assert all(
        isinstance(item["paragraph_indices"], list) and item["paragraph_indices"]
        for item in settings
    )
    finish_result = result.update["flow"].finish_task_result
    assert finish_result is not None
    assert finish_result["schema_validation"] == "passed"


def test_setting_business_validator_failure_surfaces_to_llm() -> None:
    """Live SKILL business validator (``validate_event_extraction``)
    enforces ``setting_id`` matches ``SET_<digits>``. A malformed id
    must route the response back to the model node with a Business
    diagnostic — proves the new pipeline wires validator dispatch
    end-to-end against the live SKILL's rule set.
    """
    models_module = _load(
        "skills/event-extraction/script/models.py",
        "_event_extraction_models_validator_smoke",
    )
    validators_module = _load(
        "skills/event-extraction/script/validators.py",
        "_event_extraction_validators_validator_smoke",
    )
    setting_cls: type = models_module.Setting
    validator: Callable[
        [list[dict[str, Any]]], tuple[bool, list[str]]
    ] = validators_module.validate_event_extraction

    bad_md = """
## not-a-set-id
- setting_id: not-a-set-id
- paragraph_indices: 3
- related_event_id: EVT_001
- core_knowledge: 这是足够长的核心知识描述，试图绕过最小长度阈值来测试 setting_id 格式错误时业务校验器是否生效。
"""

    middleware = CognitiveFlowMiddleware(
        IOManager([]),
        current_phase_schema=setting_cls,
        business_validator=validator,
        phase_name="settings",
    )
    request = _request(
        name="finish_task",
        args={"business_data_md": bad_md},
    )

    result = middleware.wrap_tool_call(request, _handler)

    assert isinstance(result, Command)
    assert result.goto == "model"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    text = str(message.content)
    assert "[Business]" in text
    assert "SET_数字" in text
