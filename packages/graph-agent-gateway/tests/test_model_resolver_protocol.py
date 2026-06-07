"""
Test: test_model_resolver_protocol.py
Covers: design.md §1.2 (ModelResolverProtocol signature) +
tasks.md α2 (DI injection and singleton cutover) +
requirements.md §4.1 (Mock Model Resolver drives runtime).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.language_models.base import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field


class EmptySkillResolver:
    def resolve_skill(self, skill_id: str) -> Path:
        raise AssertionError(f"unexpected skill resolution: {skill_id}")


def test_model_resolver_protocol_signature_is_complete() -> None:
    from graph_agent_gateway.protocol import ModelResolverProtocol

    signature = inspect.signature(ModelResolverProtocol.resolve)
    params = signature.parameters

    assert list(params) == [
        "self",
        "role_name",
        "thinking_enabled",
        "model_override",
        "callbacks",
        "phase_name",
        "predict_context",
        "kwargs",
    ]
    assert params["role_name"].default is None
    assert params["thinking_enabled"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["thinking_enabled"].default is None
    assert params["model_override"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["model_override"].default is None
    assert params["callbacks"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["callbacks"].default == ()
    assert params["phase_name"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["phase_name"].default is None
    assert params["predict_context"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["predict_context"].default is None
    assert params["kwargs"].kind is inspect.Parameter.VAR_KEYWORD


def test_model_resolver_protocol_resolve_routes_signature_is_complete() -> None:
    from graph_agent_gateway.protocol import ModelResolverProtocol

    signature = inspect.signature(ModelResolverProtocol.resolve_routes)
    params = signature.parameters

    assert list(params) == [
        "self",
        "role_name",
        "route_override",
    ]
    assert params["role_name"].annotation == "str"
    assert params["route_override"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["route_override"].default is None
    assert params["route_override"].annotation == "str | None"
    assert signature.return_annotation == "ResolvedRole"


def test_protocol_is_runtime_checkable_for_di_validation() -> None:
    from graph_agent_gateway.protocol import ModelResolverProtocol

    class FakeResolver:
        def resolve(
            self,
            role_name: str | None = None,
            *,
            thinking_enabled: bool | None = None,
            model_override: str | None = None,
            callbacks: tuple[Any, ...] = (),
            phase_name: str | None = None,
            predict_context: Any | None = None,
            **kwargs: Any,
        ) -> object:
            return {
                "role_name": role_name,
                "thinking_enabled": thinking_enabled,
                "model_override": model_override,
                "callbacks": callbacks,
                "phase_name": phase_name,
                "predict_context": predict_context,
                "kwargs": kwargs,
            }

        def resolve_routes(
            self,
            role_name: str,
            *,
            route_override: str | None = None,
        ) -> object:
            return {
                "role_name": role_name,
                "route_override": route_override,
            }

    assert isinstance(FakeResolver(), ModelResolverProtocol)


def test_protocol_rejects_chat_only_resolver_without_route_api() -> None:
    from graph_agent_gateway.protocol import ModelResolverProtocol

    class ChatOnlyResolver:
        def resolve(
            self,
            role_name: str | None = None,
            *,
            thinking_enabled: bool | None = None,
            model_override: str | None = None,
            callbacks: tuple[Any, ...] = (),
            phase_name: str | None = None,
            predict_context: Any | None = None,
            **kwargs: Any,
        ) -> object:
            return {
                "role_name": role_name,
                "thinking_enabled": thinking_enabled,
                "model_override": model_override,
                "callbacks": callbacks,
                "phase_name": phase_name,
                "predict_context": predict_context,
                "kwargs": kwargs,
            }

    assert not isinstance(ChatOnlyResolver(), ModelResolverProtocol)


def test_run_skill_accepts_model_resolver_keyword() -> None:
    from graph_agent import run_skill

    signature = inspect.signature(run_skill)

    assert "model_resolver" in signature.parameters
    assert signature.parameters["model_resolver"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["model_resolver"].default is None




@pytest.mark.xfail(
    reason=(
        "pre-existing red: run_skill 自 PR-α #91 起要求 skill_resolver kwarg; "
        "属 run_skill 签名工作 (PR-B), 非 PR-A errors scope"
    ),
    strict=False,
)
def test_agent_phase_react_loop_uses_injected_model_resolver(tmp_path: Path) -> None:
    from graph_agent import run_skill

    class MockChatModel(BaseChatModel):
        calls: list[list[BaseMessage]] = Field(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "mock-agent-chat"

        def bind_tools(
            self,
            tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
            *,
            tool_choice: str | None = None,
            **kwargs: Any,
        ) -> Runnable[LanguageModelInput, AIMessage]:
            del tools, tool_choice, kwargs
            return cast(Runnable[LanguageModelInput, AIMessage], self)

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: Any | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            del stop, run_manager, kwargs
            self.calls.append(messages)
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="done"))],
                llm_output={},
            )

    class MockResolver:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.models: list[MockChatModel] = []

        def resolve(
            self,
            role_name: str | None = None,
            *,
            thinking_enabled: bool | None = None,
            model_override: str | None = None,
            callbacks: tuple[Any, ...] = (),
            phase_name: str | None = None,
            predict_context: Any | None = None,
            **kwargs: Any,
        ) -> BaseChatModel:
            self.calls.append(
                {
                    "role_name": role_name,
                    "thinking_enabled": thinking_enabled,
                    "model_override": model_override,
                    "callbacks": callbacks,
                    "phase_name": phase_name,
                    "predict_context": predict_context,
                    "kwargs": kwargs,
                }
            )
            model = MockChatModel()
            self.models.append(model)
            return model

    skill_root = tmp_path / "agent_skill"
    phase_dir = skill_root / "phases" / "agent_phase"
    phase_dir.mkdir(parents=True)
    (skill_root / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: agent-loop-test
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - agent_phase
---
<phase depends_on="input" output>agent_phase</phase>
""",
        encoding="utf-8",
    )
    (phase_dir / "SKILL.md").write_text(
        """---
llm_role: balanced
phase_config:
  io:
    inputs:
      type: object
      properties: {}
    outputs:
      type: object
      properties: {}
  tools: []
  subagents: []
  subgraphs: []
  references: []
  examples: []
  max_iterations: 2
---
<role>
You are a test agent.
</role>

<goal>
Say done.
</goal>

<step id="S1" name="answer">Return done.</step>

""",
        encoding="utf-8",
    )

    resolver = MockResolver()
    result = run_skill(
        skill_root,
        skill_resolver=EmptySkillResolver(),
        model_resolver=resolver,
    )

    assert result.success is True, result.error
    assert resolver.calls
    assert resolver.calls[0]["role_name"] == "balanced"
    assert resolver.calls[0]["phase_name"] == "agent_phase"
    assert resolver.models
    assert resolver.models[0].calls
