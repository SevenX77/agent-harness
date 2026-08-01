"""Tool responses must IMMEDIATELY follow their assistant message.

Field evidence (run 2026-08-01T11-34-10, DeepSeek 400): the outgoing history
was ``System AI[a] Tool->a Human AI[b] AI Tool->b`` — every tool_call answered
*somewhere*, but a bare AI message sat between AI[b] and Tool->b. The OpenAI
protocol demands adjacency, so existence-only repair (#545) let this through.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from graph_agent.middleware.tool_history import _repair_orphaned_tool_calls


def _ai(call_id: str | None = None, content: str = "") -> AIMessage:
    if call_id is None:
        return AIMessage(content=content or "思考中")
    return AIMessage(
        content=content,
        tool_calls=[{"name": "finish_task", "args": {}, "id": call_id}],
    )


def _tool(call_id: str) -> ToolMessage:
    return ToolMessage(content="feedback", name="finish_task", tool_call_id=call_id)


def _shape(messages: list) -> list[str]:
    parts = []
    for m in messages:
        if isinstance(m, AIMessage) and m.tool_calls:
            parts.append("AI[" + ",".join(tc["id"] for tc in m.tool_calls) + "]")
        elif isinstance(m, ToolMessage):
            parts.append(f"T->{m.tool_call_id}")
        else:
            parts.append(type(m).__name__.removesuffix("Message"))
    return parts


def test_interleaved_bare_ai_is_moved_after_tool_response() -> None:
    messages = [
        SystemMessage(content="sys"),
        _ai("a"),
        _tool("a"),
        HumanMessage(content="反馈"),
        _ai("b"),
        _ai(None, "第二轮的裸回复"),
        _tool("b"),
    ]

    repaired = _repair_orphaned_tool_calls(messages)

    assert _shape(repaired) == [
        "System",
        "AI[a]",
        "T->a",
        "Human",
        "AI[b]",
        "T->b",
        "AI",
    ], "tool response must sit immediately after its assistant message"


def test_missing_response_still_synthesised_adjacent() -> None:
    messages = [_ai("x"), HumanMessage(content="打断")]

    repaired = _repair_orphaned_tool_calls(messages)

    assert _shape(repaired)[:2] == ["AI[x]", "T->x"]


def test_already_adjacent_history_untouched() -> None:
    messages = [_ai("a"), _tool("a"), _ai(None, "结语")]

    repaired = _repair_orphaned_tool_calls(messages)

    assert _shape(repaired) == ["AI[a]", "T->a", "AI"]
    assert repaired == messages
