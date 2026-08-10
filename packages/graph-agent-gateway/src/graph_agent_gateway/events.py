"""Gateway-owned event DTOs.

These are dataclasses with a hand-written ``model_dump`` rather than the host's
own Pydantic event models, and that is deliberate: the gateway does not depend
on the engine (see ``pyproject.toml`` — langchain-core and pydantic only), so it
cannot reference the engine's event contract. Each event therefore exists twice,
once on each side of that boundary, and the shapes are kept in step by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ROUTE_DECISION_EVENT_CODE = "[F-v3-gateway-llm-route-decision]"
CALL_SETTINGS_EVENT_CODE = "[F-v3-gateway-llm-call-settings]"

RouteDecision = Literal[
    "skipped_circuit_open",
    "probe_failed",
    "retried_same_route",
    "dropped_rejected_settings",
    "escalated_budget",
    "fell_back",
    "failed_terminal",
    "answered",
    "exhausted",
]


@dataclass(frozen=True)
class LLMRouteDecisionEvent:
    """One decision the gateway made while getting an answer for a role.

    Every candidate the gateway skips, probes, retries, escalates, falls back
    from or answers on is the same kind of fact with a different outcome, so
    ``decision`` is a closed set rather than this being several event types. A
    seventh outcome is a new member of that set, not a new contract.

    ``voided_streamed_answer`` is a property of the decision, not a decision of
    its own: escalating and falling back both discard whatever the abandoned
    attempt already streamed, and whoever is displaying that text needs to hear
    it from the decision that caused it.
    """

    phase_name: str
    decision: RouteDecision
    route_id: str | None = None
    endpoint_id: str | None = None
    provider_model_id: str | None = None
    protocol: str | None = None
    reason: str | None = None
    # What the provider itself said, when it said anything: 404 on a model
    # that does not exist reads very differently from 503 on an overloaded
    # one, and the reason string alone makes the reader parse for it.
    provider_status_code: int | None = None
    next_route_id: str | None = None
    voided_streamed_answer: bool = False
    code: str = field(default=ROUTE_DECISION_EVENT_CODE, init=False)
    event_type: str = field(default="llm_route_decision", init=False)

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "event_type": self.event_type,
            "phase_name": self.phase_name,
            "decision": self.decision,
            "route_id": self.route_id,
            "endpoint_id": self.endpoint_id,
            "provider_model_id": self.provider_model_id,
            "protocol": self.protocol,
            "reason": self.reason,
            "provider_status_code": self.provider_status_code,
            "next_route_id": self.next_route_id,
            "voided_streamed_answer": self.voided_streamed_answer,
            "code": self.code,
        }


@dataclass(frozen=True)
class LLMCallSettingsEvent:
    """What one call asked its route to do, and what became of each of it.

    Separate from ``LLMRouteDecisionEvent`` because they answer different
    questions: that one says which route was used and why it changed, this one
    says what parameters the answer was produced under. Two questions, two
    reasons to change.

    It is emitted when the answer closes rather than when the request goes out,
    because one of the verdicts — reasoning asked for and absent — cannot be
    known until there is an answer to read.

    The gateway defines its own copy of this shape (it does not depend on the
    engine); the two are kept in step by hand.
    """

    phase_name: str
    settings: tuple[dict[str, Any], ...]
    route_id: str | None = None
    provider_model_id: str | None = None
    protocol: str | None = None
    code: str = field(default=CALL_SETTINGS_EVENT_CODE, init=False)
    event_type: str = field(default="llm_call_settings", init=False)

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "event_type": self.event_type,
            "phase_name": self.phase_name,
            "settings": [dict(setting) for setting in self.settings],
            "route_id": self.route_id,
            "provider_model_id": self.provider_model_id,
            "protocol": self.protocol,
            "code": self.code,
        }
