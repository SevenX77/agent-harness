from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from graph_agent.callbacks.events import InterruptedEvent, ResumedEvent, RunEndedEvent
from graph_agent.core.checkpointer import reset_checkpointer
from graph_agent.core.runner import resume_skill, run_skill
from graph_agent.core.state import BusinessData, FrameworkState


class _Resolver:
    def resolve_skill(self, skill_id: str) -> Path:
        raise AssertionError(f"unexpected skill resolution for {skill_id}")


class _HitLQuestionModel(BaseChatModel):
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "hitl-question-test"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _HitLQuestionModel:
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
        self.calls += 1
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "ask_clarification",
                                "args": {
                                    "question": "Pick one?",
                                    "clarification_type": "approach_choice",
                                    "options": ["A", "B"],
                                },
                                "id": "ask-1",
                            }
                        ],
                    )
                )
            ]
        )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hitl_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: hitl-event-test
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
  max_iterations: 3
  tools:
    - ask_clarification
    - finish_task
---
<role>Executor.</role>
<goal>Ask the user to choose, then finish.</goal>
""",
    )
    _write(
        root / "phases" / "main" / "tools" / "ask.py",
        '''from __future__ import annotations

def ask_clarification(
    question: str,
    clarification_type: str = "missing_info",
    options: list[str] | None = None,
) -> str:
    return "handled by middleware"
''',
    )


def test_hitl_pause_emits_interrupted_event_with_checkpoint_and_namespace(
    tmp_path: Path,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "hitl-interrupted-event"
    _hitl_skill(skill_root)
    events: list[Any] = []

    reset_checkpointer()
    try:
        run_skill(
            skill_root,
            workspace_dir=workspace_dir,
            thread_id=run_id,
            mock_llm=_HitLQuestionModel(),
            event_subscriber=events.append,
            skill_resolver=_Resolver(),
            topic="contracts",
        )
    finally:
        reset_checkpointer()

    interrupted = [event for event in events if isinstance(event, InterruptedEvent)]
    assert len(interrupted) == 1
    event = interrupted[0]
    assert event.thread_id == run_id
    assert event.phase_name == "main"
    assert event.question == "Pick one?"
    assert event.clarification_type == "approach_choice"
    assert event.options == ["A", "B"]
    assert event.checkpoint_id
    assert event.checkpoint_ns == "agent:main"
    assert event.namespace == "agent:main"
    assert event.ns == "agent:main"

    run_ended = [event for event in events if isinstance(event, RunEndedEvent)]
    assert run_ended[-1].status == "interrupted"


def test_hitl_interrupt_detection_ignores_stale_checkpoint_in_same_namespace() -> None:
    from graph_agent.core import runner as runner_module

    run_id = "hitl-stale-checkpoint"
    tool_call = {
        "name": "ask_clarification",
        "args": {
            "question": "Pick one?",
            "clarification_type": "approach_choice",
            "options": ["A", "B"],
        },
        "id": "ask-1",
    }

    class _Checkpoint:
        def __init__(self, checkpoint_id: str, values: dict[str, Any]) -> None:
            self.config = {
                "configurable": {
                    "thread_id": run_id,
                    "checkpoint_ns": "agent:main",
                    "checkpoint_id": checkpoint_id,
                }
            }
            self.checkpoint = {"id": checkpoint_id, "channel_values": values}

    class _Checkpointer:
        def list(self, config: dict[str, Any]) -> list[_Checkpoint]:
            assert config["configurable"]["thread_id"] == run_id
            return [
                _Checkpoint(
                    "latest",
                    {
                        "messages": [
                            AIMessage(content="", tool_calls=[tool_call]),
                            ToolMessage(content="A", tool_call_id="ask-1"),
                        ]
                    },
                ),
                _Checkpoint(
                    "stale",
                    {"__pregel_tasks": [SimpleNamespace(arg={"tool_call": tool_call})]},
                ),
            ]

    assert runner_module._find_hitl_interrupt_checkpoint(_Checkpointer(), run_id, {}) is None


def test_resume_skill_emits_resumed_event_before_continuing_from_checkpoint(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    from graph_agent.core import runner as runner_module

    run_id = "hitl-resumed-event"
    checkpoint_id = "cp-hitl"
    checkpoint_ns = "agent:main"
    events: list[Any] = []

    class _FakeGraph:
        def get_state(self, config: dict[str, Any]) -> Any:
            assert config["configurable"]["checkpoint_id"] == checkpoint_id
            return SimpleNamespace(
                next=("main",),
                values={
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "ask_clarification",
                                    "args": {"question": "Pick one?"},
                                    "id": "ask-1",
                                }
                            ],
                        )
                    ]
                },
            )

        def update_state(
            self,
            config: dict[str, Any],
            update: dict[str, Any],
            *,
            as_node: str | None = None,
        ) -> dict[str, Any]:
            assert as_node == "main"
            messages = update["messages"]
            assert messages[0].content == "A"
            assert messages[0].tool_call_id == "ask-1"
            return config

        def invoke(self, value: Any, *, config: dict[str, Any]) -> dict[str, Any]:
            del value, config
            assert any(isinstance(event, ResumedEvent) for event in events)
            return {
                "data": BusinessData.model_validate({"answer": "ok"}),
                "flow": FrameworkState.model_validate(
                    {"run_id": run_id, "thread_id": run_id}
                ),
            }

    compiled = SimpleNamespace(raw={"io": {"outputs": {}}}, nodes=[])
    monkeypatch.setattr(runner_module, "_resolve_resume_checkpointer", lambda: object())
    monkeypatch.setattr(
        runner_module,
        "compile_skill",
        lambda *_args, **_kwargs: compiled,
    )
    monkeypatch.setattr(
        runner_module,
        "assemble_graph",
        lambda *_args, **_kwargs: SimpleNamespace(graph=_FakeGraph()),
    )

    resume_skill(
        tmp_path / "skill",
        workspace_dir=tmp_path / "workspace",
        run_id=run_id,
        checkpoint_id=checkpoint_id,
        checkpoint_ns=checkpoint_ns,
        human_response={"content": "A"},
        event_subscriber=events.append,
        skill_resolver=_Resolver(),
    )

    resumed = [event for event in events if isinstance(event, ResumedEvent)]
    assert len(resumed) == 1
    event = resumed[0]
    assert event.thread_id == run_id
    assert event.human_input == "A"
    assert event.resumed_from_phase == "main"
    assert event.checkpoint_id == checkpoint_id
    assert event.checkpoint_ns == checkpoint_ns
    assert event.namespace == checkpoint_ns
    assert event.ns == checkpoint_ns
