"""Probing: asking a provider a question small enough to be worth asking.

Three questions, one shape — send a minimal request and read the answer:
what models does this endpoint list, can this route generate, and does this
official call method work for this model. What each question puts on the wire
is the `dialect` domain's answer; what an answer means is `judge`'s.

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
    INCONCLUSIVE_PROBE_STATUSES,
    Answered,
    Question,
    accepted_effort_levels,
    ask_each,
    effort_questions,
)
from .results import EndpointProbeResult, RouteProbeResult
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
    "probe_status",
    "provider_response_message",
    "vendor_error_code",
]
