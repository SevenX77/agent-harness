"""ExitControlMiddleware 双闸 nudge 适配器——图级行为测试。

迁移决议 2026-08-15 §3.5:planning 闸挂 after_model(有文本、无 tool_calls、
working_memory 无 "plan" 键),selfcheck/standard 闸挂 after_agent(无合格
finish_task → nudge + jump_to "model" 回灌);事件统一 typed NudgeEvent;
预算耗尽后按既有 [F-v3-agent-exit-control-failed] 语义显式失败,不静默 END。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill
from graph_agent.middleware.nudge_policy import PLANNING_NUDGE


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def nudges(self) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == "nudge"]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_nudge_skill(root: Path, *, max_iterations: int = 6) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: nudge-exit-gate-adapter
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
---
<role>
Nudge adapter verifier.
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


def _finish_call(call_id: str) -> dict[str, Any]:
    return {
        "name": "finish_task",
        "args": {
            "reasoning": "nudge received; submitting the final answer now",
            "diagnostics_md": "plan reviewed step by step; output matches schema",
            "business_data_md": "## main\n- answer: nudged-through\n",
        },
        "id": call_id,
    }


def _saw_human_message_containing(messages: list[Any], needle: str) -> bool:
    return any(
        isinstance(message, HumanMessage) and needle in str(message.content)
        for message in messages
    )


class PlanningNudgeThenFinishModel:
    """轮 1 纯文本 → 应吃到 planning nudge → 轮 2 直接 finish。"""

    def __init__(self) -> None:
        self.invocations = 0
        self.saw_planning_nudge = False

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> PlanningNudgeThenFinishModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.invocations += 1
        if self.invocations == 1:
            return AIMessage(content="Let me describe my approach in prose only.")
        self.saw_planning_nudge = _saw_human_message_containing(
            messages, "update_working_memory"
        )
        return AIMessage(content="", tool_calls=[_finish_call("finish-after-planning")])


class PlanFirstThenTextThenFinishModel:
    """轮 1 写 plan → 轮 2 纯文本(planning 不得再触发)→ 应吃到 standard nudge。"""

    def __init__(self) -> None:
        self.invocations = 0
        self.saw_standard_nudge = False
        self.saw_planning_nudge = False

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> PlanFirstThenTextThenFinishModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.invocations += 1
        if self.invocations == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "update_working_memory",
                        "args": {"plan": "1. lookup 2. finish_task with the answer"},
                        "id": "plan-1",
                    }
                ],
            )
        if self.invocations == 2:
            return AIMessage(content="The plan is recorded; musing in prose again.")
        self.saw_planning_nudge = _saw_human_message_containing(messages, PLANNING_NUDGE)
        self.saw_standard_nudge = _saw_human_message_containing(
            messages, "你输出了文本但未调用 finish_task"
        )
        return AIMessage(content="", tool_calls=[_finish_call("finish-after-standard")])


class AlwaysTextModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> AlwaysTextModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        self.invocations += 1
        return AIMessage(content="I only ever talk and never call tools.")


def test_planning_nudge_fires_on_first_text_only_turn(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_nudge_skill(skill_root)
    chat = PlanningNudgeThenFinishModel()
    recorder = Recorder()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        callbacks=[recorder],
        topic="planning",
    )

    assert chat.invocations == 2
    assert chat.saw_planning_nudge is True
    assert result.success is True
    assert result.context.get("answer") == "nudged-through"

    (nudge,) = recorder.nudges()
    assert nudge.phase_name == "main"
    assert nudge.nudge_type == "planning"
    assert nudge.nudge_count == 1
    assert nudge.message, "机器决定必须整句发声(machinery-speaks D4)"


def test_standard_nudge_fires_when_plan_exists(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_nudge_skill(skill_root)
    chat = PlanFirstThenTextThenFinishModel()
    recorder = Recorder()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        callbacks=[recorder],
        topic="standard",
    )

    assert chat.invocations == 3
    assert chat.saw_planning_nudge is False, "plan 已写入,planning 闸不得重复教育"
    assert chat.saw_standard_nudge is True
    assert result.success is True

    (nudge,) = recorder.nudges()
    assert nudge.nudge_type == "standard"
    assert nudge.nudge_count == 1


def test_nudge_budget_exhaustion_fails_explicitly(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_nudge_skill(skill_root, max_iterations=6)
    chat = AlwaysTextModel()
    recorder = Recorder()

    result = run_skill(
        skill_root,
        mock_llm=chat,
        workspace_dir=tmp_path / "workspace",
        skill_resolver=mock_skill_resolver,
        callbacks=[recorder],
        topic="exhaustion",
    )

    # max_nudges=1 → planning 1 次 + standard 1 次 = 全局上限 2×,第三轮显式失败。
    assert result.success is False
    assert "[F-v3-agent-exit-control-failed]" in str(result.error)
    assert chat.invocations == 3
    assert [n.nudge_type for n in recorder.nudges()] == ["planning", "standard"]
    assert result.context.get("answer") is None


def test_nudge_budget_is_scoped_per_graph_invoke(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_nudge_skill(skill_root)

    class NudgeAwareModel:
        def __init__(self) -> None:
            self.invocations = 0

        def bind_tools(self, tools: list[Any], **kwargs: Any) -> NudgeAwareModel:
            del tools, kwargs
            return self

        def invoke(self, messages: list[Any]) -> AIMessage:
            self.invocations += 1
            if _saw_human_message_containing(messages, "update_working_memory"):
                return AIMessage(
                    content="", tool_calls=[_finish_call(f"finish-{self.invocations}")]
                )
            return AIMessage(content="prose first, tools later")

    chat = NudgeAwareModel()
    recorder = Recorder()
    compiled = compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
        callbacks=[recorder],
    ).graph

    for thread_id in ("run-1", "run-2"):
        final_state = graph.invoke(
            {"data": {"topic": "scope"}, "flow": {"thread_id": thread_id}, "messages": []},
            config={"configurable": {"thread_id": thread_id}},
        )
        assert final_state["data"].model_dump()["answer"] == "nudged-through"

    # 每个 invoke 各自一条 planning nudge:预算按 thread 隔离,不跨 run 累积。
    assert [(n.nudge_type, n.nudge_count) for n in recorder.nudges()] == [
        ("planning", 1),
        ("planning", 1),
    ]
