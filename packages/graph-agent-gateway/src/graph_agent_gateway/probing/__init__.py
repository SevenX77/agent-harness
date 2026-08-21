"""Probing: asking a provider a question small enough to be worth asking.

Three questions, one shape — send a minimal request and read the answer:
what models does this endpoint list, can this route generate, and does this
official call method work for this model. What each question puts on the wire
is the `dialect` domain's answer; what an answer means is `judge`'s.

A fourth question does not fit that shape and has its own module. Whether a
route enters a tool loop and comes back out takes two turns and a control value
the model cannot know, so `tool_loop` owns the whole question: what it sends,
what the answer means, and how far the route got.

The results are evidence, not truth: writing them into the registry is the
host's decision, made through the registry's own contract.
"""

from __future__ import annotations

from .judge import (
    ProviderAnswer,
    ProviderProbeStatus,
    model_capabilities,
    model_ids,
    probe_status,
    provider_response_message,
    vendor_error_code,
)
from .questions import (
    EFFORT_CONTROL_LEVEL,
    INCONCLUSIVE_PROBE_STATUSES,
    Answered,
    Question,
    accepted_effort_levels,
    ask_each,
    effort_questions,
)
from .results import EndpointProbeResult, RouteProbeResult, RouteToolLoopResult, ToolLoopReach
from .tool_loop import (
    TOOL_LOOP_PROBE_PROMPT,
    TOOL_LOOP_PROBE_SUBJECT,
    TOOL_LOOP_PROBE_TOOL,
    TOOL_LOOP_PROBE_TOOL_NAME,
    probe_route_tool_loop,
)
from .wire import (
    OfficialCallMethod,
    endpoint_probe_base_url,
    probe_official_call_method,
    probe_provider_endpoint,
    probe_provider_route,
)

__all__ = [
    "Answered",
    "EndpointProbeResult",
    "OfficialCallMethod",
    "ProviderAnswer",
    "ProviderProbeStatus",
    "Question",
    "RouteProbeResult",
    "RouteToolLoopResult",
    "ToolLoopReach",
    "TOOL_LOOP_PROBE_PROMPT",
    "TOOL_LOOP_PROBE_SUBJECT",
    "TOOL_LOOP_PROBE_TOOL",
    "TOOL_LOOP_PROBE_TOOL_NAME",
    "EFFORT_CONTROL_LEVEL",
    "accepted_effort_levels",
    "ask_each",
    "INCONCLUSIVE_PROBE_STATUSES",
    "effort_questions",
    "endpoint_probe_base_url",
    "model_capabilities",
    "model_ids",
    "probe_official_call_method",
    "probe_provider_endpoint",
    "probe_provider_route",
    "probe_route_tool_loop",
    "probe_status",
    "provider_response_message",
    "vendor_error_code",
]
