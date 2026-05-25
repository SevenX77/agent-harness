"""RED-LIGHT tests for PR β clarification parity and runtime integration."""

from __future__ import annotations

import inspect


def test_ask_clarification_attended_path_keeps_interrupt_semantics() -> None:
    """Unit parity: attended clarification must keep interrupt behavior."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
    from graph_agent.tools.builtin.clarification_tool import ask_clarification_tool

    interrupts: list[dict[str, object]] = []

    def interrupt_fn(payload: dict[str, object]) -> str:
        interrupts.append(payload)
        return "human answer"

    intercept = CognitiveFlowMiddleware.intercept_ask_clarification
    result = intercept(
        tool=ask_clarification_tool,
        args={"question": "Need input?"},
        state={"phase": "main"},
        unattended=False,
        interrupt_fn=interrupt_fn,
    )

    assert result.answer == "human answer"
    assert interrupts == [{"question": "Need input?", "phase": "main"}]


def test_ask_clarification_unattended_path_returns_conservative_auto_answer() -> None:
    """Unit parity: unattended clarification must keep conservative auto-answer behavior."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
    from graph_agent.tools.builtin.clarification_tool import ask_clarification_tool

    intercept = CognitiveFlowMiddleware.intercept_ask_clarification
    result = intercept(
        tool=ask_clarification_tool,
        args={"question": "Need input?"},
        state={"phase": "main"},
        unattended=True,
        interrupt_fn=None,
    )

    assert result.answer
    assert result.source == "unattended_auto_answer"


def test_non_cognitive_tools_pass_through_middleware_chain() -> None:
    """Unit parity: non finish_task / ask_clarification tools must pass through unchanged."""

    from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware

    calls: list[tuple[str, dict[str, object]]] = []

    def handler(tool_name: str, args: dict[str, object]) -> dict[str, object]:
        calls.append((tool_name, args))
        return {"ok": True, "tool_name": tool_name, "args": args}

    dispatch = CognitiveFlowMiddleware.dispatch_tool_call
    result = dispatch(
        tool_name="read_reference",
        args={"path": "docs/engine/README.md"},
        state={"phase": "main"},
        handler=handler,
    )

    assert result == {
        "ok": True,
        "tool_name": "read_reference",
        "args": {"path": "docs/engine/README.md"},
    }
    assert calls == [("read_reference", {"path": "docs/engine/README.md"})]


def test_agent_runtime_finish_task_flows_through_middleware_not_graph_assembler_decision() -> None:
    """Integration/e2e parity: Agent finish_task must not be decided inside graph_assembler."""

    from graph_agent.core import graph_assembler
    from graph_agent.middleware.factory import build_middleware_chain

    agent_path_source = inspect.getsource(graph_assembler)

    assert callable(build_middleware_chain)
    assert "build_middleware_chain" in agent_path_source
    assert 'flow["finish_task_result"]' not in agent_path_source
    assert 'if name == "finish_task"' not in agent_path_source
