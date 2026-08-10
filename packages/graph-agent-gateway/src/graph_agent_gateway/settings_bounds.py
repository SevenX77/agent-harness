"""What one route will take for one setting, and how a value is made to fit.

A preference only means something inside a range. Temperature runs to 1.0 on
one protocol and 2.0 on another; a model sells three effort levels while its
neighbour sells six; every model has a most output tokens it will produce.
Offering a value from outside that range spends a round trip to be told
something the route had already said about itself.

Fitting happens before the request is built, and it is deliberately narrow: a
bound this module cannot source is not a bound, and a value it cannot rank is
not adjusted. Anything it leaves alone still meets the refusal path, which is
the honest place for "we did not know".

Where bounds come from is decided by whether they vary:

- Fixed by the protocol's API contract (temperature scale, top_p ceiling) —
  a constant here, because probing re-learns a documented number every time.
- Varying by model with no documented per-model answer (effort levels) — the
  route's own capabilities, filled by probing it.

Decision: docs/design/2026-08-10-preferences-fit-the-route-decision.md
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from graph_agent_gateway.registry.schema import ResolvedRoute

# Studio's own dial, which the frontend shows as 0-100%. Provider scales are
# reached by taking that share of the route's ceiling, so a value past the end
# of the dial means "as hot as this route goes", never "hotter than it goes".
AUTHORED_TEMPERATURE_MAX: Final = 2.0

_PROTOCOL_TEMPERATURE_MAX: Final[Mapping[str, float]] = {
    "anthropic_compatible": 1.0,
    "openai_compatible": 2.0,
    "ark_runtime": 2.0,
    "google_genai": 2.0,
    "wavespeed_any_llm": 2.0,
}

# Nucleus sampling names a share of the probability mass, and every protocol we
# speak caps it at all of it.
_TOP_P_MAX: Final = 1.0

# Effort levels weakest first. No provider sells all of them and they disagree
# on which subset, so the ladder exists to make "the nearest level below"
# answerable; membership of it is not a claim that any model has that level.
EFFORT_LADDER: Final[tuple[str, ...]] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

# Which rungs each protocol's request can name at all. This is the protocol's
# vocabulary, not any model's menu: a name outside it cannot be spelled in that
# request body, so no measuring can discover it. Protocols left out say nothing
# about levels — OpenAI's set moves per model version — and are answered by
# measuring the route instead.
_PROTOCOL_EFFORT_LEVELS: Final[Mapping[str, tuple[str, ...]]] = {
    "anthropic_compatible": ("low", "medium", "high", "xhigh", "max"),
    "google_genai": ("minimal", "low", "medium", "high"),
}


@dataclass(frozen=True)
class Bounds:
    """The range a route accepts for one setting, as far as anything knows it."""

    minimum: float | None = None
    maximum: float | None = None
    allowed: tuple[str, ...] = ()

    @property
    def known(self) -> bool:
        """Whether anything is known — an unknown bound must not be clamped against."""
        return self.minimum is not None or self.maximum is not None or bool(self.allowed)


def bounds_for(route: ResolvedRoute, name: str) -> Bounds:
    """The range this route accepts for the named setting.

    Names are the registry's setting names (``reasoning.effort``), not the
    keyword arguments a request is built from: a bound belongs to the setting,
    and the same setting reaches different providers under different keys.
    """
    if name == "temperature":
        return Bounds(minimum=0.0, maximum=AUTHORED_TEMPERATURE_MAX)
    if name == "top_p":
        return Bounds(minimum=0.0, maximum=_TOP_P_MAX)
    if name == "max_output_tokens":
        return Bounds(
            minimum=_capability_number(route, "min_output_tokens"),
            maximum=_capability_number(route, "max_output_tokens"),
        )
    if name == "reasoning.effort":
        return Bounds(allowed=_effort_levels(route))
    if name == "reasoning.budget_tokens":
        return Bounds(minimum=_capability_number(route, "min_thinking_budget_tokens"))
    return Bounds()


def fit(value: Any, bounds: Bounds) -> Any:
    """The nearest value to ``value`` that ``bounds`` accepts.

    Returned unchanged when there is no bound to fit to, when the value is
    absent, or when it cannot be ranked against the bound — each of those is a
    case where clamping would be inventing an answer.
    """
    if value is None or not bounds.known:
        return value
    if bounds.allowed:
        return _nearest_level(value, bounds.allowed)
    return _clamped(value, bounds)


def temperature_ceiling(route: ResolvedRoute) -> float:
    """The hottest this route runs, as the route says or as its protocol does."""
    declared = _capability_number(route, "temperature", field="max")
    if declared is not None:
        return declared
    return _PROTOCOL_TEMPERATURE_MAX.get(str(route.protocol), AUTHORED_TEMPERATURE_MAX)


def provider_temperature_from_authored(
    temperature: float | int | None,
    route: ResolvedRoute,
) -> float | None:
    """Map Studio's authored temperature onto the share of this route's ceiling."""
    if temperature is None:
        return None
    share = float(fit(float(temperature), bounds_for(route, "temperature")))
    return share / AUTHORED_TEMPERATURE_MAX * temperature_ceiling(route)


def _clamped(value: Any, bounds: Bounds) -> Any:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    fitted: float = value
    if bounds.minimum is not None:
        fitted = max(fitted, bounds.minimum)
    if bounds.maximum is not None:
        fitted = min(fitted, bounds.maximum)
    return int(fitted) if isinstance(value, int) else fitted


def _nearest_level(value: Any, allowed: tuple[str, ...]) -> Any:
    if not isinstance(value, str) or value in allowed:
        return value
    ranked = sorted(
        (EFFORT_LADDER.index(level), level) for level in allowed if level in EFFORT_LADDER
    )
    if not ranked or value not in EFFORT_LADDER:
        return value
    asked = EFFORT_LADDER.index(value)
    below = [level for rank, level in ranked if rank <= asked]
    return below[-1] if below else ranked[0][1]


def _effort_levels(route: ResolvedRoute) -> tuple[str, ...]:
    """The effort levels this route takes, measured if it has been, documented if not.

    A measurement outranks the protocol's vocabulary: the vocabulary says which
    names are spellable, and only the model says which of them it actually sells.
    """
    measured = _capability_levels(route, "reasoning_effort")
    if measured:
        return measured
    return _PROTOCOL_EFFORT_LEVELS.get(str(route.protocol), ())


def _capability_value(route: ResolvedRoute, key: str) -> Any:
    capability = route.capabilities.get(key)
    return getattr(capability, "value", None)


def _capability_number(
    route: ResolvedRoute,
    key: str,
    *,
    field: str = "max",
) -> float | None:
    value = _capability_value(route, key)
    if isinstance(value, Mapping):
        value = value.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _capability_levels(route: ResolvedRoute, key: str) -> tuple[str, ...]:
    value = _capability_value(route, key)
    if not isinstance(value, Mapping):
        return ()
    levels = value.get("values")
    if not isinstance(levels, list):
        return ()
    return tuple(level for level in levels if isinstance(level, str))


__all__ = [
    "AUTHORED_TEMPERATURE_MAX",
    "EFFORT_LADDER",
    "Bounds",
    "bounds_for",
    "fit",
    "provider_temperature_from_authored",
    "temperature_ceiling",
]
