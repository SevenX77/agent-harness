from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill
from graph_agent.core.state import StateManager


class NoFinishChatModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> NoFinishChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.invocations += 1
        return AIMessage(content="I am done, but I did not call finish_task.")


class NudgeThenFinishChatModel:
    def __init__(self) -> None:
        self.invocations = 0
        self.saw_finish_nudge = False

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> NudgeThenFinishChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.invocations += 1
        if self.invocations == 1:
            return AIMessage(content="I have enough information and forgot the tool call.")

        self.saw_finish_nudge = any(
            type(message).__name__ == "HumanMessage"
            and "finish_task" in str(getattr(message, "content", ""))
            for message in messages
        )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "nudge received; submitting final answer",
                        "diagnostics_md": "exit gate asked for an explicit finish marker",
                        "business_data_md": "## main\n- answer: after-nudge\n",
                    },
                    "id": "finish-after-nudge",
                }
            ],
        )


class LoopingToolChatModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> LoopingToolChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.invocations += 1
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup",
                    "args": {"topic": "exit-gate"},
                    "id": f"lookup-{self.invocations}",
                }
            ],
        )


class FinishImmediatelyChatModel:
    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FinishImmediatelyChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "done with explicit marker",
                        "diagnostics_md": "schema and exit marker are aligned",
                        "business_data_md": "## main\n- answer: complete\n",
                    },
                    "id": "finish-immediate",
                }
            ],
        )


class AfterAgentExitGateSentinel(AgentMiddleware[Any]):
    def after_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any]:
        del runtime
        flow = state["flow"]
        working_memory = getattr(flow, "working_memory", {})
        if not isinstance(working_memory, dict):
            working_memory = {"value": working_memory}
        working_memory = dict(working_memory)
        working_memory["exit_gate_after_agent_seen"] = True
        next_state = StateManager.update_framework(state, working_memory=working_memory)
        return {"flow": next_state["flow"]}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_exit_gate_skill(root: Path, *, max_iterations: int = 2) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e8-exit-gate-red
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
max_iterations: {max_iterations}
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
tools:
  - lookup
  - finish_task
---
<role>
Exit gate verifier.
</role>
<goal>
Use tools as needed, then call @tool:finish_task with the final answer.
</goal>
<protocol id="P1">
The phase is not complete until finish_task accepts business_data_md.
</protocol>
""",
    )
    _write(
        root / "phases" / "main" / "tools" / "lookup.py",
        "def lookup(topic: str) -> str:\n"
        "    return f'lookup:{topic}'\n",
    )


def test_agent_without_finish_task_returns_explicit_failure(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root)
    chat = NoFinishChatModel()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        topic="exit-gate",
    )

    assert result.success is False
    assert result.error is not None or result.diagnostics
    assert result.context.get("answer") is None
    assert chat.invocations >= 1


def test_no_tool_calls_gets_nudged_back_to_model_before_success(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root)
    chat = NudgeThenFinishChatModel()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        topic="exit-gate",
    )

    assert chat.invocations >= 2
    assert chat.saw_finish_nudge is True
    assert result.success is True
    assert result.context.get("answer") == "after-nudge"


def test_max_iterations_exhaustion_is_failure_not_empty_success(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root, max_iterations=2)
    chat = LoopingToolChatModel()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        topic="exit-gate",
    )

    assert result.success is False
    assert result.error is not None or result.diagnostics
    assert result.context.get("answer") is None
    assert chat.invocations == 2


def test_finish_task_marker_preserves_schema_fields_and_business_output(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root)
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=FinishImmediatelyChatModel(),
        skill_resolver=mock_skill_resolver,
    ).graph

    final_state = graph.invoke(
        {"data": {"topic": "exit-gate"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )

    finish_result = final_state["flow"].finish_task_result
    assert finish_result is not None
    assert finish_result["reasoning"] == "done with explicit marker"
    assert finish_result["diagnostics_md"] == "schema and exit marker are aligned"
    assert finish_result["business_data_md"].strip() == "## main\n- answer: complete"
    assert finish_result["schema_validation"] == "passed"
    assert final_state["data"].model_dump()["answer"] == "complete"


def test_finish_task_success_must_pass_through_after_agent_exit_gate(
    tmp_path: Path,
    mock_skill_resolver: object,
    monkeypatch: Any,
) -> None:
    import graph_agent.middleware.factory as middleware_factory

    original_build_middleware_chain = middleware_factory.build_middleware_chain

    def build_chain_with_after_agent_sentinel(**kwargs: Any) -> tuple[Any, ...]:
        return (*original_build_middleware_chain(**kwargs), AfterAgentExitGateSentinel())

    monkeypatch.setattr(
        middleware_factory,
        "build_middleware_chain",
        build_chain_with_after_agent_sentinel,
    )

    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root)
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=FinishImmediatelyChatModel(),
        skill_resolver=mock_skill_resolver,
    ).graph

    final_state = graph.invoke(
        {"data": {"topic": "exit-gate"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )

    assert final_state["data"].model_dump()["answer"] == "complete"
    working_memory = final_state["flow"].working_memory
    assert isinstance(working_memory, dict)
    assert working_memory.get("exit_gate_after_agent_seen") is True


def test_exit_gate_iteration_budget_is_scoped_to_each_graph_invoke(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_exit_gate_skill(skill_root, max_iterations=2)

    class ReusedGraphChatModel:
        def __init__(self) -> None:
            self.invocations = 0

        def bind_tools(self, tools: list[Any], **kwargs: Any) -> ReusedGraphChatModel:
            del tools, kwargs
            return self

        def invoke(self, messages: list[Any]) -> AIMessage:
            self.invocations += 1
            if self.invocations == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "finish_task",
                            "args": {
                                "reasoning": "done with explicit marker",
                                "diagnostics_md": "aligned",
                                "business_data_md": "## main\n- answer: complete\n",
                            },
                            "id": "finish-1",
                        }
                    ],
                )
            return AIMessage(content="I am done, no tool calls.")

    chat = ReusedGraphChatModel()
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
    ).graph

    # 1. 第一次调用：成功完成，消耗 1 次模型调用
    state1 = graph.invoke(
        {"data": {"topic": "exit-gate"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )
    assert state1["data"].model_dump()["answer"] == "complete"
    assert chat.invocations == 1

    # 2. 第二次调用：应当有 2 次模型调用预算
    import pytest

    from graph_agent.core.exceptions import GraphAgentFatalError

    with pytest.raises(GraphAgentFatalError) as exc_info:
        graph.invoke(
            {"data": {"topic": "exit-gate"}, "flow": {"thread_id": "run-2"}, "messages": []},
            config={"configurable": {"thread_id": "run-2"}},
        )

    # 验证第二次执行是否有足够的预算（总共 3 次 invocations）
    assert chat.invocations == 3
    assert "[F-v3-agent-exit-control-failed]" in str(exc_info.value)
