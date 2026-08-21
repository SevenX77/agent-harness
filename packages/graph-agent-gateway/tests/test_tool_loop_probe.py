"""T3: can this route enter a ReAct loop, and does it come back out.

The probe that was missing. Four Test buttons could say a route was reachable,
that it generated, that it took an effort level — and none of them could say
whether it calls a tool, which is what every agent phase in the engine actually
depends on (`graph_agent/core/llm_provider.py` binds tools on every loop).

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
D1's T3 row and P5.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from graph_agent_gateway.probing import (
    TOOL_LOOP_PROBE_TOOL,
    TOOL_LOOP_PROBE_TOOL_NAME,
    probe_route_tool_loop,
)
from graph_agent_gateway.registry import ProviderEndpoint, ProviderRoute
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import SecretStr

SECRET = "A3F91C7B"


def _endpoint(protocol: str = "openai_compatible") -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id="endpoint-one",
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://host.example/v1",
        api_key=SecretStr("SECRET"),
    )


def _route() -> ProviderRoute:
    return ProviderRoute(
        route_id="endpoint-one:m-1",
        endpoint_id="endpoint-one",
        route_slug="m-1",
        provider_model_id="m-1",
    )


def _tool_call(call_id: str = "call-1") -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": TOOL_LOOP_PROBE_TOOL_NAME,
                "args": {"subject": "harbor"},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


class _ScriptedModel:
    """Answers each `ainvoke` with the next scripted turn, and records the input.

    A turn may be an exception, because a route that dies on the SECOND request
    is one of the outcomes this probe has to report distinctly from one that
    never called the tool at all.
    """

    def __init__(self, *turns: Any) -> None:
        self.turns = list(turns)
        self.inputs: list[Any] = []
        self.bound_tools: list[Any] | None = None

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ScriptedModel:
        del kwargs
        self.bound_tools = list(tools)
        return self

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        self.inputs.append(messages)
        turn = self.turns.pop(0)
        if isinstance(turn, BaseException):
            raise turn
        return turn


class _FactorySpy:
    def __init__(self, model: Any) -> None:
        self.model = model
        self.builds: list[dict[str, Any]] = []

    def build(self, route: Any, **kwargs: Any) -> Any:
        self.builds.append({"route_id": route.route_id, "kwargs": kwargs})
        return self.model


def _auth_error() -> BaseException:
    import openai

    request = httpx.Request("POST", "https://host.example/v1/chat/completions")
    return openai.AuthenticationError(
        "bad key",
        response=httpx.Response(401, json={"error": {"message": "bad key"}}, request=request),
        body=None,
    )


@pytest.mark.anyio
async def test_the_probe_binds_its_tool_through_the_production_factory() -> None:
    """The probe is only worth having if it asked the way a run asks.

    Production binds tools onto a model the factory built (`call/chat_model.py`
    `_dispatch`). A probe that hand-rolled a `tools` array would be predicting a
    request nobody sends.
    """
    model = _ScriptedModel(_tool_call(), AIMessage(content=f"The code is {SECRET}."))
    factory = _FactorySpy(model)

    await probe_route_tool_loop(_endpoint(), _route(), factory=factory, secret=SECRET)

    assert [build["route_id"] for build in factory.builds] == ["endpoint-one:m-1"]
    assert model.bound_tools == [TOOL_LOOP_PROBE_TOOL]


@pytest.mark.anyio
async def test_a_route_that_calls_the_tool_and_repeats_the_result_closed_the_loop() -> None:
    model = _ScriptedModel(_tool_call(), AIMessage(content=f"The code is {SECRET}."))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "closed_the_loop"
    assert result.status == "ok"
    assert result.called_the_tool is True
    assert result.closed_the_loop is True


@pytest.mark.anyio
async def test_the_tool_result_goes_back_as_a_tool_message_on_the_call_it_answers() -> None:
    """L2 is the loop, so the second turn has to look like a loop's second turn.

    A tool result delivered as anything but a `ToolMessage` carrying the id of
    the call it answers is a different conversation, and what came back would
    say nothing about whether this route can run an agent.
    """
    model = _ScriptedModel(_tool_call("call-7"), AIMessage(content=SECRET))

    await probe_route_tool_loop(_endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET)

    second_turn = model.inputs[1]
    tool_messages = [message for message in second_turn if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in tool_messages] == ["call-7"]
    assert [message.content for message in tool_messages] == [SECRET]


@pytest.mark.anyio
async def test_a_route_that_answers_in_prose_never_entered_the_loop() -> None:
    """Answering without calling is an answer about the route, not a failure.

    The provider took the request — it just did not use the tool. That is a
    different fact from "this endpoint refused us", and spending a second
    request on it would be asking a question whose premise never held.
    """
    model = _ScriptedModel(AIMessage(content="I do not have access to that."))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "answered_without_calling"
    assert result.status == "ok"
    assert result.called_the_tool is False
    assert len(model.inputs) == 1


@pytest.mark.anyio
async def test_an_answer_that_does_not_carry_the_secret_did_not_close_the_loop() -> None:
    """The secret is the control, and it is why this probe can be believed.

    Without a value the model cannot know, "it read the tool result" and "it
    made up something plausible" arrive as the same final sentence — exactly
    the confusion `EFFORT_CONTROL_LEVEL` exists to prevent for effort levels.
    """
    model = _ScriptedModel(_tool_call(), AIMessage(content="The code is 12345678."))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "called_the_tool"
    assert result.closed_the_loop is False
    assert result.message is not None


@pytest.mark.anyio
async def test_a_second_tool_call_instead_of_an_answer_is_not_a_closed_loop() -> None:
    """One feedback turn, and the bound is deliberate.

    Borrowed from LangChain's own `AgentExecutor`, which bounds a ReAct loop by
    iteration count rather than by hope. Rejected: its default of 15, because
    this probe pays a real request per turn and its question is binary — does
    the route come back out — not "can it finish a task". So the bound is one,
    and a route still looping at that point is recorded as having called the
    tool, which is true, instead of as having converged, which is unproven.
    """
    model = _ScriptedModel(_tool_call("call-1"), _tool_call("call-2"))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "called_the_tool"
    assert len(model.inputs) == 2


@pytest.mark.anyio
async def test_a_tool_call_with_no_id_cannot_be_answered_and_says_so() -> None:
    """A call the probe cannot reply to stops the loop where it stopped.

    Recording it as "answered without calling" would delete a tool call that
    demonstrably happened; recording it as a closed loop would claim a turn that
    was never sent.
    """
    model = _ScriptedModel(_tool_call(""))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "called_the_tool"
    assert len(model.inputs) == 1
    assert result.message is not None


@pytest.mark.anyio
async def test_a_route_that_never_answered_reaches_nothing_and_reports_why() -> None:
    model = _ScriptedModel(_auth_error())

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "no_answer"
    assert result.status == "invalid_key"


@pytest.mark.anyio
async def test_a_failure_on_the_second_turn_keeps_the_ground_the_first_turn_won() -> None:
    """`status` says why it stopped; `reach` says how far it got.

    They are two different facts, and collapsing them would either throw away a
    tool call that really happened or report a route as healthy when its second
    request died.
    """
    model = _ScriptedModel(_tool_call(), _auth_error())

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.reach == "called_the_tool"
    assert result.status == "invalid_key"


@pytest.mark.anyio
async def test_the_probe_names_the_route_it_probed() -> None:
    model = _ScriptedModel(AIMessage(content="no"))

    result = await probe_route_tool_loop(
        _endpoint(), _route(), factory=_FactorySpy(model), secret=SECRET
    )

    assert result.route_id == "endpoint-one:m-1"
    assert result.endpoint_id == "endpoint-one"
    assert result.model_id == "m-1"
    assert result.base_url == "https://host.example/v1"


@pytest.mark.anyio
async def test_an_endpoint_with_no_key_is_refused_before_a_request_is_spent() -> None:
    endpoint = ProviderEndpoint(
        endpoint_id="endpoint-one",
        protocol="openai_compatible",
        base_url="https://host.example/v1",
        api_key=None,
    )
    model = _ScriptedModel(AIMessage(content="unreachable"))
    factory = _FactorySpy(model)

    result = await probe_route_tool_loop(endpoint, _route(), factory=factory, secret=SECRET)

    assert result.status == "invalid_key"
    assert result.reach == "no_answer"
    assert factory.builds == []


def test_the_probe_tool_is_a_function_the_probe_prompt_names() -> None:
    """The prompt has to be unanswerable without the tool, or a prose reply
    would be a correct answer and the measurement would mean nothing."""
    from graph_agent_gateway.probing import TOOL_LOOP_PROBE_PROMPT

    assert TOOL_LOOP_PROBE_TOOL["type"] == "function"
    function = TOOL_LOOP_PROBE_TOOL["function"]
    assert isinstance(function, dict)
    assert function["name"] == TOOL_LOOP_PROBE_TOOL_NAME
    assert TOOL_LOOP_PROBE_TOOL_NAME in TOOL_LOOP_PROBE_PROMPT
