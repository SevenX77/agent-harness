from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent import assemble_graph, compile_skill
from langchain_core.messages import AIMessage

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = REPO_ROOT / "skills" / "producer"


class FakeProducerChatModel:
    def __init__(self) -> None:
        self.bound_tools: list[Any] = []
        self.critic_invocations = 0
        self.react_turns = 0

    def bind_tools(self, tools: list[Any]) -> FakeProducerChatModel:
        self.bound_tools = tools
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        last_text = str(getattr(messages[-1], "content", "")) if messages else ""
        if "You are a critic. Review the text against the criteria." in last_text:
            self.critic_invocations += 1
            return AIMessage(
                content=json.dumps(
                    {
                        "passed": True,
                        "reasons": ["视觉冲击力和断点刺激达标"],
                        "suggestions": ["继续强化道具尺度和情绪反差"],
                    },
                    ensure_ascii=False,
                )
            )

        self.react_turns += 1
        if self.react_turns == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "reviewer",
                        "args": {
                            "target_text": "主角拖着巨刃走入雨夜废墟，镜头压低，断点停在广播响起。",
                            "criteria": "按爽剧制片人标准审核视觉冲击力、续看率和分享率。",
                        },
                        "id": "producer-reviewer-1",
                    }
                ],
            )

        review = {
            "producer_review": {
                "passed": True,
                "score": 8,
                "verdict": "approved",
                "reasons": ["视觉压迫感明确", "断点具备续看钩子"],
                "suggestions": ["增加一处可截图的材质细节"],
                "critic_metadata": {"critic_invocations": self.critic_invocations},
            }
        }
        markdown = "## producer_review\n\n```json\n" + json.dumps(
            review["producer_review"], ensure_ascii=False
        ) + "\n```"
        return AIMessage(
            content="",
            tool_calls=[{"name": "finish_task", "args": {"markdown": markdown}, "id": "producer-finish"}],
        )


def test_producer_v21_e2e_actor_critic_fake_llm() -> None:
    chat = FakeProducerChatModel()
    compiled = compile_skill(SKILL_ROOT, cache=False)
    graph = assemble_graph(compiled, chat_model=chat).graph

    result = graph.invoke(
        {
            "data": {
                "content": "主角拖着巨刃走入雨夜废墟，镜头压低，断点停在广播响起。",
                "contexts": ["visual", "pacing"],
                "criteria": "审核视觉冲击力、续看率和分享率。",
                "artifact_type": "storyboard",
            },
            "flow": {},
            "messages": [],
            "run_id": "producer-v21-test",
        }
    )

    review = result["data"]["producer"]["producer_review"]
    assert review["passed"] is True
    assert review["score"] == 8
    assert result["flow"]["critic_metrics"]["reviewer"]["invocations"] >= 1
    assert chat.critic_invocations == 1
    assert any(tool.name == "reviewer" for tool in chat.bound_tools)
    assert result["flow"]["finish_task_result"]["ok"] is True


def test_producer_v21_compile_and_assemble() -> None:
    compiled = compile_skill(SKILL_ROOT, cache=False)
    assembled = assemble_graph(compiled)

    assert compiled.manifest.name == "producer"
    assert [phase.id for phase in compiled.manifest.phases] == ["producer"]
    assert compiled.manifest.phases[0].depends_on == []
    assert assembled.graph is not None


def test_producer_review_subskill_removed() -> None:
    assert not (SKILL_ROOT / "review").exists()
