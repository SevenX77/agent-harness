"""An agent node must account for what it spent and say which model spent it.

The V4 agent node (``graph_assembler._build_skill_node``) is the live phase
runtime, and it emits its own ``LLMCallEvent`` — unlike the legacy LLM phase
node, which routes through ``_HarnessCallbackBridge``. Three things the bridge
does were missing on the agent path, so a real run produced a trace nobody could
account from (observed 2026-08-08 on exp-b-round7 run
2026-08-07T11-39-40_a20015ec: 28 llm_call events totalling 374140 input tokens,
``metrics.json`` reporting ``total_tokens: 0``, and no model name anywhere):

* the tokens were never folded into the run's metrics;
* the micro events carried no ``parent_node_id`` / ``node_type``, so they could
  not be attributed to the agent node they came from
  (docs/engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md §8 #1);
* the resolved model was dropped, although the provider puts it on the message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from graph_agent.callbacks.events import CallbackEvent
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill

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
name: agent-node-observability
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


class _OneShotChatModel(BaseChatModel):
    """Answers once, reporting usage and the model the provider actually used."""

    calls: list[list[dict[str, Any]]] = Field(
        default_factory=lambda: [
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
        ]
    )

    @property
    def _llm_type(self) -> str:
        return "agent-node-observability"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _OneShotChatModel:
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        message = AIMessage(
            content="",
            tool_calls=self.calls.pop(0) if self.calls else [],
            response_metadata={"model_name": "deepseek-v4-flash"},
            usage_metadata={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _Recorder:
    def __init__(self) -> None:
        self.events: list[CallbackEvent] = []

    def on_event(self, event: CallbackEvent) -> None:
        self.events.append(event)


def _run(tmp_path: Path, mock_skill_resolver: object) -> tuple[dict[str, Any], _Recorder]:
    _agent_skill(tmp_path)
    recorder = _Recorder()
    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=_OneShotChatModel(),
        skill_resolver=mock_skill_resolver,
        callbacks=[recorder],
    ).graph
    result = graph.invoke(
        {
            "data": {"topic": "contracts"},
            "flow": {"run_id": "run-1", "thread_id": "run-1"},
            "messages": [],
        },
        config={"configurable": {"thread_id": "run-1"}},
    )
    return result, recorder


def test_agent_node_folds_its_tokens_into_the_run_metrics(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    result, _ = _run(tmp_path, mock_skill_resolver)

    metrics = result["flow"].metrics
    assert metrics["total_input_tokens"] == 3
    assert metrics["total_output_tokens"] == 5


def test_agent_node_llm_call_says_which_node_and_which_model(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _, recorder = _run(tmp_path, mock_skill_resolver)

    llm_calls = [event for event in recorder.events if event.event_type == "llm_call"]
    assert llm_calls, "the agent node must emit an llm_call event"
    call = llm_calls[0]
    assert call.parent_node_id == "main"
    assert call.node_type == "agent"
    assert call.resolved_model == "deepseek-v4-flash"


def test_agent_node_tool_call_is_attributed_to_its_node(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _, recorder = _run(tmp_path, mock_skill_resolver)

    tool_calls = [event for event in recorder.events if event.event_type == "tool_call"]
    assert tool_calls, "the agent node must emit a tool_call event"
    assert tool_calls[0].parent_node_id == "main"
    assert tool_calls[0].node_type == "agent"


def test_run_result_metrics_report_the_tokens_the_run_actually_spent(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    """``metrics.json`` must report the run's real token spend, not a zero.

    Both phase runtimes accumulate into ``flow.metrics``; the runner is what
    turns a finished graph into a ``RunResult``, so it owes that state to the
    caller. Observed 2026-08-08 on exp-b-round7 run
    2026-08-08T12-53-23_f90d8d60: 11 llm_call events totalling 120073 input
    tokens, ``metrics.json`` still reporting ``total_tokens: 0``.
    """
    skill_root = tmp_path / "skill"
    _agent_skill(skill_root)

    result = run_skill(
        skill_root,
        mock_llm=_OneShotChatModel(),
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        topic="contracts",
    )

    assert result.success is True
    assert result.metrics.input_tokens == 3
    assert result.metrics.output_tokens == 5
    assert result.metrics.total_tokens == 8
    assert result.metrics.wall_time_sec > 0.0
