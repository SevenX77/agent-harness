"""RED tests for WS-E5 inner checkpoint namespace contracts."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from graph_agent.core import graph_assembler
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import (
    NamespaceCheckpointer,
    _run_graph_loop_iterate,
    active_outer_ns,
    assemble_graph,
)
from graph_agent.core.manifest import IterateAccumulateSpec, IterateSpec
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _FinishTaskChatModel(BaseChatModel):
    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "ws-e5-finish-task"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _FinishTaskChatModel:
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        if messages and isinstance(messages[-1], ToolMessage):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])

        self.call_count += 1
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "checkpoint-ready",
                        "diagnostics_md": "ws-e5",
                        "business_data_md": f"## item\n- answer: ok-{self.call_count}\n",
                    },
                    "id": f"finish-{self.call_count}",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _agent_skill(root: Path, *, graph_iterate: str | None = None) -> None:
    iterate_block = f"{graph_iterate.rstrip()}\n" if graph_iterate else ""
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e5-checkpoint-inner-red
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      topics:
        type: array
        items:
          type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
{iterate_block}phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
      topics:
        type: array
        items:
          type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
max_iterations: 3
llm_role: graph_agent
---
<role>
Checkpoint boundary verifier.
</role>
<goal>
Call @tool:finish_task with final business data.
</goal>
""",
    )


def _invoke_agent_graph(
    root: Path,
    mock_skill_resolver: object,
    *,
    saver: InMemorySaver,
    data: dict[str, Any],
    thread_id: str = "thread-red",
) -> dict[str, Any]:
    compiled = compile_skill(root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=_FinishTaskChatModel(),
        skill_resolver=mock_skill_resolver,
        checkpointer=saver,
    ).graph
    return graph.invoke(
        {
            "data": data,
            "flow": {"thread_id": thread_id, "run_id": thread_id},
            "messages": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )


def _checkpoint_namespaces(saver: InMemorySaver, thread_id: str) -> list[str]:
    checkpoints = list(saver.list({"configurable": {"thread_id": thread_id}}))
    return [
        str(checkpoint.config.get("configurable", {}).get("checkpoint_ns", ""))
        for checkpoint in checkpoints
    ]


def _business_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result["data"]
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return dict(data)


def _flow_data(result: dict[str, Any]) -> dict[str, Any]:
    flow = result["flow"]
    if hasattr(flow, "model_dump"):
        return flow.model_dump()
    return dict(flow)


def test_agent_inner_checkpoint_writes_to_shared_thread_and_namespace(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    saver = InMemorySaver()

    result = _invoke_agent_graph(
        tmp_path,
        mock_skill_resolver,
        saver=saver,
        data={"topic": "checkpoint"},
        thread_id="thread-agent",
    )

    namespaces = _checkpoint_namespaces(saver, "thread-agent")
    assert "" in namespaces, "outer graph checkpoints must remain queryable in the shared base"
    assert any("agent" in namespace and "main" in namespace for namespace in namespaces), (
        "AGENT inner loop must write checkpoints under a stable agent namespace "
        "in the same thread/base checkpointer"
    )
    business = _business_data(result)
    assert business["answer"].startswith("ok-")
    assert not any(key.startswith("_") for key in business)
    for forbidden_key in (
        "messages",
        "tool_calls",
        "checkpoint_ns",
        "configurable",
        "runtime",
        "callbacks",
        "compiled_graph",
    ):
        assert forbidden_key not in business
    flow = _flow_data(result)
    assert flow["thread_id"] == "thread-agent"
    assert flow["run_id"] == "thread-agent"


def test_agent_inside_graph_iterate_preserves_iteration_namespace(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(
        tmp_path,
        graph_iterate=dedent(
            """
            iterate:
              mode: batch
              over: data.topics
              item_var: topic
              concurrency: 1
            """
        ),
    )
    saver = InMemorySaver()

    _invoke_agent_graph(
        tmp_path,
        mock_skill_resolver,
        saver=saver,
        data={"topics": ["a", "b"]},
        thread_id="thread-iterate-agent",
    )

    namespaces = _checkpoint_namespaces(saver, "thread-iterate-agent")
    assert any("iter1" in namespace and "agent" in namespace for namespace in namespaces), (
        "agent checkpoints created inside graph iterate round 1 must preserve both "
        f"the iteration namespace and the agent namespace; saw {namespaces!r}"
    )
    assert any("iter2" in namespace and "agent" in namespace for namespace in namespaces), (
        "agent checkpoints created inside graph iterate round 2 must preserve both "
        f"the iteration namespace and the agent namespace; saw {namespaces!r}"
    )


def test_history_queries_distinguish_outer_and_agent_checkpoints(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    saver = InMemorySaver()

    _invoke_agent_graph(
        tmp_path,
        mock_skill_resolver,
        saver=saver,
        data={"topic": "history"},
        thread_id="thread-history",
    )

    outer = saver.get_tuple({"configurable": {"thread_id": "thread-history", "checkpoint_ns": ""}})
    agent = saver.get_tuple(
        {"configurable": {"thread_id": "thread-history", "checkpoint_ns": "agent:main"}}
    )

    assert outer is not None
    assert agent is not None
    assert outer.config.get("configurable", {}).get("checkpoint_ns", "") == ""
    assert agent.config.get("configurable", {}).get("checkpoint_ns", "") == "agent:main"
    assert outer.checkpoint["id"] != agent.checkpoint["id"]


def test_agent_inner_invoke_uses_sync_durability_with_shared_checkpointer(
    monkeypatch: Any,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    saver = InMemorySaver()
    captured_invoke_kwargs: dict[str, Any] = {}

    class _FakeCompiledAgent:
        def get_graph(self) -> Any:
            class _GraphShape:
                nodes = ["__start__", "model", "__end__"]

            return _GraphShape()

        def invoke(
            self,
            payload: dict[str, Any],
            config: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> WorkflowState:
            del config
            captured_invoke_kwargs.update(kwargs)
            return WorkflowState(
                data=BusinessData.model_validate({"answer": "sync"}),
                flow=payload["flow"],
                messages=payload["messages"],
            )

    def fake_create_agent(**kwargs: Any) -> _FakeCompiledAgent:
        del kwargs
        return _FakeCompiledAgent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=_FinishTaskChatModel(),
        skill_resolver=mock_skill_resolver,
        checkpointer=saver,
    ).graph

    graph.invoke(
        {
            "data": {"topic": "sync"},
            "flow": {"thread_id": "thread-sync", "run_id": "thread-sync"},
            "messages": [],
        },
        config={"configurable": {"thread_id": "thread-sync"}},
    )

    assert captured_invoke_kwargs.get("durability") == "sync"


def test_finish_task_framework_meta_stays_out_of_business_data() -> None:
    state = WorkflowState(
        data=BusinessData(),
        flow=FrameworkState(thread_id="thread-state"),
        messages=[],
    )

    with pytest.raises(ValueError):
        StateManager.update_business(state, _checkpoint_ns="agent:main")

    routed = StateManager.route_finish_task(
        state,
        {
            "answer": "ok",
            "_checkpoint_ns": "agent:main",
            "_runtime_marker": "inner",
        },
    )

    assert routed["data"].model_dump() == {"answer": "ok"}
    assert routed["flow"].finish_task_result == {
        "meta": {"_checkpoint_ns": "agent:main", "_runtime_marker": "inner"},
        "raw": {
            "answer": "ok",
            "_checkpoint_ns": "agent:main",
            "_runtime_marker": "inner",
        },
    }


def test_graph_loop_iterate_does_not_leak_iteration_namespace_to_later_agent_checkpoint() -> None:
    class _FakeGraph:
        def invoke(
            self,
            child_state: WorkflowState,
            config: dict[str, Any] | None = None,
            **kwargs: Any,
        ) -> WorkflowState:
            del config, kwargs
            data = child_state["data"].model_dump()
            data["piece"] = data["topic"]
            return WorkflowState(
                data=BusinessData.model_validate(data),
                flow=child_state["flow"],
                messages=child_state["messages"],
            )

    token = active_outer_ns.set("")
    try:
        state = WorkflowState(
            data=BusinessData.model_validate({"topics": ["a", "b"]}),
            flow=FrameworkState(thread_id="thread-loop"),
            messages=[],
        )
        iterate = IterateSpec(
            mode="loop",
            over="data.topics",
            item_var="topic",
            accumulate=IterateAccumulateSpec(
                var="answers",
                init=[],
                from_="piece",
                merge="append",
            ),
        )

        result = _run_graph_loop_iterate(
            _FakeGraph(),
            state,
            iterate,
            {"properties": {"piece": {}}},
            ["main"],
            config={"configurable": {"thread_id": "thread-loop"}},
            invoke_kwargs={},
        )
        assert result["data"].model_dump()["answers"] == ["a", "b"]

        wrapped = NamespaceCheckpointer(InMemorySaver(), "agent:main")
        later_config = wrapped._wrap_config(
            {"configurable": {"thread_id": "later-thread", "checkpoint_ns": "agent:main"}}
        )

        assert active_outer_ns.get() == ""
        assert later_config["configurable"]["checkpoint_ns"] == "agent:main"
    finally:
        active_outer_ns.reset(token)
