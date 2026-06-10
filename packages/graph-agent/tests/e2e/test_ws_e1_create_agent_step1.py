from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph

VALID_BUSINESS_MD = """## item-1
- answer: ok
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e1-create-agent-e2e
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
        """---
phase_config:
  max_iterations: 2
  tools:
    - finish_task
---
<role>
Executor.
</role>
<goal>
Call @tool:finish_task with final business data.
</goal>
""",
    )


class _TargetFinishTaskChatModel(BaseChatModel):
    calls: list[list[dict[str, Any]]] = Field(default_factory=lambda: [
        [
            {
                "name": "finish_task",
                "args": {
                    "reasoning": "done",
                    "diagnostics_md": "checked",
                    "business_data_md": VALID_BUSINESS_MD,
                },
                "id": "finish-1",
            }
        ]
    ])
    bound_tool_names: list[str] = Field(default_factory=list)
    generated_messages: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "ws-e1-target-finish-task"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _TargetFinishTaskChatModel:
        del kwargs
        self.bound_tool_names = [str(getattr(tool, "name", "")) for tool in tools]
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        tool_calls = self.calls.pop(0) if self.calls else []
        message = AIMessage(
            content="",
            tool_calls=tool_calls,
            response_metadata={
                "token_usage": {"prompt_tokens": 3, "completion_tokens": 5},
                "thinking_blocks": [{"type": "thinking", "text": "ready"}],
                "tool_call_metadata": {"source": "fake-gateway"},
            },
            usage_metadata={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
        )
        self.generated_messages.append(message)
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_agent_create_agent_loop_finishes_with_target_schema_and_inner_checkpoint(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path)
    chat = _TargetFinishTaskChatModel()
    checkpointer = InMemorySaver()

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
        checkpointer=checkpointer,
    ).graph

    try:
        result = graph.invoke(
            {
                "data": {"topic": "contracts"},
                "flow": {"run_id": "run-1", "thread_id": "run-1"},
                "messages": [],
            },
            config={"configurable": {"thread_id": "run-1"}},
        )
    except Exception as exc:  # noqa: BLE001 - RED must expose the live schema drift clearly
        pytest.fail(
            "AGENT create_agent path must accept finish_task raw args "
            "(reasoning, diagnostics_md, business_data_md) and route them through "
            f"CognitiveFlow; current path raised {type(exc).__name__}: {exc}"
        )

    flow = result["flow"]
    finish_result = flow.finish_task_result
    assert finish_result is not None
    assert finish_result["business_data_md"] == VALID_BUSINESS_MD.strip()
    assert finish_result["business_data_parsed"] == [{"answer": "ok"}]

    visible_messages = list(result["messages"])
    assert any(getattr(message, "usage_metadata", None) for message in visible_messages)
    assert any(
        getattr(message, "response_metadata", {}).get("thinking_blocks")
        for message in visible_messages
    )
    assert any(
        getattr(message, "response_metadata", {}).get("tool_call_metadata")
        for message in visible_messages
    )

    checkpoints = list(checkpointer.list({"configurable": {"thread_id": "run-1"}}))
    print("=== checkpointer.storage.keys() ===", list(checkpointer.storage.keys()))
    namespaces = [
        str(checkpoint.config.get("configurable", {}).get("checkpoint_ns", ""))
        for checkpoint in checkpoints
    ]
    print("=== namespaces ===", namespaces)
    assert any("main" in namespace and "agent" in namespace for namespace in namespaces)
    assert not any(callable(value) for value in flow.model_dump().values())
