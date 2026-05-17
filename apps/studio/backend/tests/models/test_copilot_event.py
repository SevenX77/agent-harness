from __future__ import annotations

import pytest
from app.models.copilot import (
    ContextUpdateRequest,
    CopilotEvent,
    CopilotEventDone,
    CopilotEventError,
    CopilotEventText,
    CopilotEventToolUseResult,
    CopilotEventToolUseStart,
)
from pydantic import TypeAdapter, ValidationError


def test_copilot_event_subclasses_construct() -> None:
    assert CopilotEventText(content="hello").type == "text_delta"
    assert CopilotEventToolUseStart(
        tool_name="Read", tool_input={"file_path": "SKILL.md"}
    ).type == ("tool_use_start")
    assert (
        CopilotEventToolUseResult(
            tool_name="Edit",
            success=True,
            result_summary="Edited SKILL.md: +1 -0",
        ).type
        == "tool_use_result"
    )
    assert CopilotEventDone().type == "done"
    assert CopilotEventError(message="failed").type == "error"


def test_tool_use_start_restricts_tool_name() -> None:
    with pytest.raises(ValidationError):
        CopilotEventToolUseStart(tool_name="Delete", tool_input={})


@pytest.mark.parametrize(
    "event",
    [
        CopilotEventText(content="hello"),
        CopilotEventToolUseStart(tool_name="Bash", tool_input={"command": "pwd"}),
        CopilotEventToolUseResult(tool_name="Bash", success=True, result_summary="ok"),
        CopilotEventDone(),
        CopilotEventError(message="failed"),
    ],
)
def test_copilot_event_union_round_trips(event: CopilotEvent) -> None:
    adapter = TypeAdapter(CopilotEvent)

    validated = adapter.validate_python(event.model_dump())

    assert validated == event


def test_context_update_request_accepts_timestamp() -> None:
    request = ContextUpdateRequest(
        view="Edit",
        context={"skill_md_text": "---\nname: demo\n---"},
        timestamp=1_765_000_000_000,
    )

    assert request.timestamp == 1_765_000_000_000


def test_context_update_request_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ContextUpdateRequest.model_validate(
            {
                "view": "Edit",
                "context": {},
                "timestamp": 1,
                "extra": "nope",
            }
        )
