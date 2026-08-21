"""What a probe reports back.

Evidence about one endpoint or one route at one moment: what was asked, what
came back, how long it took. Writing any of it into the registry is the host's
decision, not the probe's.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from graph_agent_gateway.registry import ProviderKind, ProviderProbeBackend

from .judge import ProviderProbeStatus


class EndpointProbeResult(BaseModel):
    """Connectivity result for one provider endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    model_ids: tuple[str, ...] = ()
    model_capabilities: dict[str, dict[str, Any]] = Field(default_factory=dict)
    message: str | None = None
    error_code: str | None = None

    @property
    def model_seen(self) -> str | None:
        return self.model_ids[0] if self.model_ids else None


class RouteProbeResult(BaseModel):
    """Generation probe result for one provider route."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    route_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    model_id: str
    status: ProviderProbeStatus
    latency_ms: int | None = None
    message: str | None = None


ToolLoopReach = Literal[
    "no_answer",
    "answered_without_calling",
    "called_the_tool",
    "closed_the_loop",
]
"""How far into a tool loop one route got, as a ladder rather than a set of flags.

Each rung implies every rung below it, so the one word says everything two or
three booleans would — and, unlike booleans, it cannot record "came back out of
a loop it never entered". 让非法状态不可表示 is cheaper here than validating it
away afterwards.

The rungs, in order: the provider never answered at all; it answered but used
prose instead of the tool; it called the tool; it took the tool's result and
came back out with a final answer carrying it.
"""


class RouteToolLoopResult(BaseModel):
    """What one route did when it was handed a tool it needed (T3).

    `status` and `reach` answer different questions and neither substitutes for
    the other: `status` says why the probe stopped, `reach` says how far it got
    before stopping. A route whose second request dies has `status` naming the
    failure and `reach` still holding the tool call it really made.
    """

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    route_id: str
    provider_kind: ProviderKind
    backend: ProviderProbeBackend
    base_url: str
    model_id: str
    status: ProviderProbeStatus
    reach: ToolLoopReach
    latency_ms: int | None = None
    message: str | None = None

    @property
    def called_the_tool(self) -> bool:
        """Whether this route was watched calling the tool it was given.

        Read by hosts deciding whether to record the measurement, so that the
        rule "which rungs count as a tool call" has exactly one home.
        """
        return self.reach in ("called_the_tool", "closed_the_loop")

    @property
    def closed_the_loop(self) -> bool:
        return self.reach == "closed_the_loop"
