"""What became of each setting one call asked for.

The gateway already knows, at the moment an answer closes, everything needed to
say this: which settings the caller chose, which of them this protocol can even
carry, which the provider refused, which had to be moved to fit, and — for the
one setting an answer can testify about — whether it visibly took effect.
Nothing here goes and asks anybody; it reads what the call already recorded.

Two of the verdicts exist to stop this from lying. ``sent`` is the honest answer
for the many settings whose effect nothing in the response can confirm:
reporting them as applied would be a claim nobody checked, and reporting them as
ignored would be an accusation nobody can support. ``ignored`` is reserved for
the case where the answer actively contradicts the request.

Only what a user chose is judged. A provider default nobody picked is not a
preference, and a table where most rows are defaults is a table where the rows
that matter cannot be found.

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from graph_agent_gateway.call.settings import KWARG_OF_SETTING, ActualRuntimeSettings

SettingVerdict = Literal["applied", "sent", "adjusted", "unsupported", "rejected", "ignored"]

# What a call's own keyword arguments settle. Not one of the resolver's
# provenance values — the host chose it for this call, past whatever the route
# had settled — so it is named here rather than found in that closed set.
CALL_OVERRIDE: Final = "call_override"

# Where a value has to come from for it to be somebody's choice rather than a
# floor we picked on their behalf. Everything else the resolver can stamp —
# profile, protocol, studio and capability defaults — is ours, and reporting
# ours back drowns theirs.
AUTHORED_SOURCES: Final[frozenset[str]] = frozenset({"route_setting", CALL_OVERRIDE})

# The one setting whose effect the answer itself can testify to: asking for
# reasoning and receiving none is a contradiction, where asking for a
# temperature and receiving prose is not.
REASONING_ENABLED: Final = "reasoning.enabled"


@dataclass(frozen=True)
class SettingOutcome:
    """One setting the caller chose, and what became of it."""

    setting: str
    requested: Any
    verdict: SettingVerdict
    reason: str | None = None

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        del mode
        return {
            "setting": self.setting,
            "requested": self.requested,
            "verdict": self.verdict,
            "reason": self.reason,
        }


def judge_settings(
    *,
    reported: ActualRuntimeSettings,
    carried: Mapping[str, str],
    refused: Sequence[str],
    reasoned: bool | None,
) -> tuple[SettingOutcome, ...]:
    """One verdict per setting the caller chose, in the order they were settled.

    ``carried`` is the protocol's own request-key map, so "this protocol has no
    place to put it" is read from the thing that builds the request rather than
    from a second list describing it. ``reasoned`` says whether the finished
    answer contained reasoning, or is ``None`` when nothing observed it.
    """
    refused_settings = {_setting_of_kwarg(name) for name in refused}
    return tuple(
        _judged(setting, record, carried, refused_settings, reasoned)
        for setting, record in reported.items()
        if str(record.get("source", "")) in AUTHORED_SOURCES
    )


def _judged(
    setting: str,
    record: Mapping[str, Any],
    carried: Mapping[str, str],
    refused: set[str],
    reasoned: bool | None,
) -> SettingOutcome:
    requested = _requested_value(record)
    if setting in refused:
        return SettingOutcome(setting, requested, "rejected", "the provider refused this value")
    if setting == REASONING_ENABLED:
        return _judged_reasoning(requested, record, reasoned)
    keyword = KWARG_OF_SETTING.get(setting, setting)
    if keyword not in carried:
        return SettingOutcome(
            setting,
            requested,
            "unsupported",
            "this protocol's request has no place to put it",
        )
    if "asked" in record:
        return SettingOutcome(
            setting,
            requested,
            "adjusted",
            f"outside what this route takes; sent as {record.get('value')}",
        )
    return SettingOutcome(setting, requested, "sent", None)


def _judged_reasoning(
    requested: Any,
    record: Mapping[str, Any],
    reasoned: bool | None,
) -> SettingOutcome:
    """Reasoning answers for itself, so it is not asked of the request-key map.

    Every protocol carries reasoning, but none of them carries it as one of the
    flat runtime keys — it travels as a thinking payload, a provider profile's
    extra body, or a request mapper. Reading its support out of that map would
    call it unsupported on routes that reason perfectly well. It needs no such
    reading: the finished answer says whether reasoning happened.
    """
    if record.get("value") is not True or reasoned is None:
        return SettingOutcome(REASONING_ENABLED, requested, "sent", None)
    if reasoned:
        return SettingOutcome(REASONING_ENABLED, requested, "applied", "the answer reasoned")
    return SettingOutcome(
        REASONING_ENABLED,
        requested,
        "ignored",
        "asked for, accepted, and the answer contains no reasoning",
    )


def _requested_value(record: Mapping[str, Any]) -> Any:
    """What the caller asked for, which is not what was sent once it was moved."""
    for key in ("asked", "authored_value", "value"):
        if key in record:
            return record[key]
    return None


def _setting_of_kwarg(keyword: str) -> str:
    for setting, mapped in KWARG_OF_SETTING.items():
        if mapped == keyword:
            return setting
    return keyword


__all__ = [
    "AUTHORED_SOURCES",
    "CALL_OVERRIDE",
    "SettingOutcome",
    "SettingVerdict",
    "judge_settings",
]
