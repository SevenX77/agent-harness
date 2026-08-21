"""T3: whether a route enters a tool loop, and whether it comes back out.

The other probes ask whether a route can be reached, whether it generates, and
which values it accepts. None of them touches the one thing every agent phase
depends on — `call/chat_model.py` `_dispatch` binds tools onto the model it
built, and a route that never emits a tool call cannot run an agent no matter
how healthy the other three answers look.

Two rungs, because they fail separately. **L1** hands the route one tool and a
question that cannot be answered without it, and reads whether a tool call came
back. **L2** answers that call and reads whether the route came out of the loop
with the result in its hands. A model can do the first and never do the second,
and a host that only knew "supports tools" would be unable to tell those apart.

The request goes out the way a run's does — `RouteChatModelFactory.build` then
`bind_tools`, the same two lines `_dispatch` runs — because a probe that
hand-rolled a `tools` array would be predicting a request nobody sends.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md,
D1's T3 row ("T3 必须走生产同一条调用路径") and P5.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Mapping, Sequence
from typing import Any, Final

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from graph_agent_gateway.registry import (
    ProviderEndpoint,
    ProviderRoute,
    provider_backend_for_protocol,
)

from .judge import ProviderProbeStatus, answer_from_failed_call, probe_status
from .results import RouteToolLoopResult, ToolLoopReach
from .wire import (
    endpoint_probe_base_url,
    probe_elapsed_ms,
    route_probe_identity,
    route_probe_model,
    route_probe_secret,
)

__all__ = [
    "TOOL_LOOP_PROBE_PROMPT",
    "TOOL_LOOP_PROBE_SUBJECT",
    "TOOL_LOOP_PROBE_TOOL",
    "TOOL_LOOP_PROBE_TOOL_NAME",
    "probe_route_tool_loop",
]


TOOL_LOOP_PROBE_TOOL_NAME: Final[str] = "graph_agent_gateway_probe_lookup"
TOOL_LOOP_PROBE_SUBJECT: Final[str] = "harbor"

TOOL_LOOP_PROBE_TOOL: Final[dict[str, Any]] = {
    "type": "function",
    "function": {
        "name": TOOL_LOOP_PROBE_TOOL_NAME,
        "description": (
            "Look up the access code for a subject. The code is stored only here "
            "and cannot be derived, guessed, or recalled from anywhere else."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "The subject whose access code to look up.",
                },
            },
            "required": ["subject"],
        },
    },
}
"""The one tool this probe offers, in the shape production sends.

An OpenAI-shaped function dict rather than a Python callable, because that is
what `bind_tools` normalises everything else INTO (`chat_model._normalise_tool`)
— starting there means what goes on the wire during a probe is the same object
production would put there, with no conversion in between to differ.

The description states the code is not derivable. That sentence is doing work:
without it a model may reasonably answer from what it thinks it knows, and a
prose answer would then be a correct answer rather than evidence about tools.
"""

TOOL_LOOP_PROBE_PROMPT: Final[str] = (
    f"Call the {TOOL_LOOP_PROBE_TOOL_NAME} tool to look up the access code for "
    f"'{TOOL_LOOP_PROBE_SUBJECT}', then reply with only that code and nothing else."
)
"""A question with exactly one path to an answer, and a short way back out.

"reply with only that code" is what makes L2 cheap and readable: the second turn
is a handful of tokens, and the answer either carries the secret or does not.
"""


# One feedback turn, and no more. Borrowed from LangChain's own `AgentExecutor`,
# which bounds a ReAct loop by iteration count rather than by hoping it stops;
# rejected: its default of 15, because that bound is sized for finishing a task
# while this probe's question is binary — does the route come back out — and
# every extra turn is a real request the user pays for. A route still calling
# tools at the bound is recorded as having called the tool, which is true,
# rather than as having converged, which this probe did not see.
_FEEDBACK_TURNS: Final[int] = 1

# Enough for a tool call's arguments plus a short final answer. The sibling
# generation probe pays for one token; one token here would truncate the tool
# call itself, and a truncated call reads exactly like "did not call the tool" —
# the one confusion this probe exists to remove.
_MAX_TOKENS: Final[int] = 256

_DEFAULT_TIMEOUT: Final[float] = 30.0


async def probe_route_tool_loop(
    endpoint: ProviderEndpoint,
    route: ProviderRoute,
    *,
    api_key: str | None = None,
    runtime_settings: Mapping[str, Any] | None = None,
    secret: str | None = None,
    factory: Any | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> RouteToolLoopResult:
    """Hand this route a tool it needs, and report how far into the loop it got.

    ``secret`` is the control. It is the value the tool returns and the value the
    final answer has to carry, and it is unguessable by construction — without
    it, "the route read the tool result" and "the route made up a plausible
    code" arrive as the same sentence, which is the same trap
    `EFFORT_CONTROL_LEVEL` exists to keep out of the effort measurement. Callers
    pass one only to make a test reproducible; a real probe mints its own.
    """

    identity = route_probe_identity(endpoint, route)
    base_url = endpoint_probe_base_url(endpoint)
    if not base_url:
        return _stopped(identity, "error", "no_answer", message="Base URL is empty.")
    if not route_probe_secret(endpoint, api_key):
        return _stopped(identity, "invalid_key", "no_answer", message="API key is empty.")

    code = secret or secrets.token_hex(4).upper()
    started = time.perf_counter()
    bound = route_probe_model(
        endpoint,
        route,
        api_key=api_key,
        runtime_settings=runtime_settings,
        factory=factory,
        timeout=timeout,
        max_tokens=_MAX_TOKENS,
    ).bind_tools([TOOL_LOOP_PROBE_TOOL])

    conversation: list[BaseMessage] = [HumanMessage(content=TOOL_LOOP_PROBE_PROMPT)]
    reach: ToolLoopReach = "no_answer"
    for _ in range(_FEEDBACK_TURNS + 1):
        try:
            answer = await bound.ainvoke(conversation)
        except BaseException as exc:  # noqa: BLE001 - every failure is an answer about the route
            return _stopped(
                identity,
                _status_of(exc, endpoint),
                reach,
                message=str(exc),
                latency_ms=probe_elapsed_ms(started),
            )

        call_id = _probe_tool_call_id(answer)
        if call_id is None:
            if reach == "no_answer":
                return _stopped(
                    identity,
                    "ok",
                    "answered_without_calling",
                    message="This route answered without calling the tool it was given.",
                    latency_ms=probe_elapsed_ms(started),
                )
            if _carries(answer, code):
                return _stopped(identity, "ok", "closed_the_loop", latency_ms=probe_elapsed_ms(started))
            return _stopped(
                identity,
                "ok",
                "called_the_tool",
                message=(
                    "This route called the tool but its answer did not carry the result, "
                    "so the loop was not observed closing."
                ),
                latency_ms=probe_elapsed_ms(started),
            )

        reach = "called_the_tool"
        if not call_id.strip():
            return _stopped(
                identity,
                "ok",
                reach,
                message=(
                    "This route called the tool without an id to answer, so the tool result "
                    "could not be sent back."
                ),
                latency_ms=probe_elapsed_ms(started),
            )
        conversation = [*conversation, answer, ToolMessage(content=code, tool_call_id=call_id)]

    return _stopped(
        identity,
        "ok",
        reach,
        message="This route was still calling tools after its result was returned.",
        latency_ms=probe_elapsed_ms(started),
    )


def _probe_tool_call_id(answer: Any) -> str | None:
    """The id of this answer's call to the probe tool, or `None` if it made none.

    An empty string is a distinct third case — a call happened, and it cannot be
    answered — so it is returned rather than folded into `None`.
    """
    calls = getattr(answer, "tool_calls", None)
    if not isinstance(calls, Sequence):
        return None
    for call in calls:
        if isinstance(call, Mapping) and call.get("name") == TOOL_LOOP_PROBE_TOOL_NAME:
            call_id = call.get("id")
            return call_id if isinstance(call_id, str) else ""
    return None


def _carries(answer: Any, code: str) -> bool:
    """Whether the final answer repeats the code the tool returned.

    Case-insensitive and substring, because the question is whether the value
    reached the answer, not whether the model formatted it a particular way.
    """
    content = getattr(answer, "content", "")
    return code.lower() in _text_of(content).lower()


def _text_of(content: Any) -> str:
    """The words in a message, whether the provider sent one string or blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return " ".join(_text_of(part) for part in content)
    if isinstance(content, Mapping):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    return ""


def _status_of(exc: BaseException, endpoint: ProviderEndpoint) -> ProviderProbeStatus:
    """What a failed turn says about the route, read the way a run's failure is."""
    answer = answer_from_failed_call(exc)
    if answer is None:
        return "timeout" if isinstance(exc, TimeoutError) else "network_error"
    return probe_status(
        answer,
        model_not_found_status="invalid_model",
        probed_backend=provider_backend_for_protocol(endpoint.protocol),
    )


def _stopped(
    identity: Mapping[str, Any],
    status: ProviderProbeStatus,
    reach: ToolLoopReach,
    *,
    message: str | None = None,
    latency_ms: int | None = None,
) -> RouteToolLoopResult:
    return RouteToolLoopResult(
        **identity,
        status=status,
        reach=reach,
        message=message,
        latency_ms=latency_ms,
    )


