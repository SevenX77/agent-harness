"""What one call asks a provider for, and which parts of it are only wishes.

A request carries two kinds of thing, and the difference only shows when a
provider refuses one of them.

Some of it *is* the call: the token budget, the tools, the shape the answer has
to come back in, the method to call it with. Drop any of that and the caller
gets something it never asked for, or something it cannot parse.

The rest is how the caller would *like* the answer produced — temperature,
top_p, seed, stop sequences, whether to reason and how hard. A provider that
will not take one of those still has the answer; it just will not tune it.

Holding the two apart inside one value is what lets the gateway ask the same
route a second time without its preferences when a provider refuses one,
instead of reading a refused parameter as a route that is down. This is also
the only place that knows what a call asks for, so it is the place that says
what the answer should report having asked for.

Three layers decide each setting, weakest first: the chat model's own
configuration, the route's effective runtime settings, and this call's keyword
arguments.

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from graph_agent_gateway.registry.schema import ResolvedRoute
from graph_agent_gateway.settings_bounds import (
    bounds_for,
    fit,
    provider_temperature_from_authored,
)

# One runtime setting as the finished answer describes it: the value that was
# asked for and where that value came from.
ActualRuntimeSettings = dict[str, dict[str, object]]


@dataclass(frozen=True)
class ModelDefaults:
    """What the chat model was configured with, before route or call speak.

    ``runtime_setting_sources`` names where the caller's own configuration came
    from, per setting key; a key marked ``call_override`` means the host chose
    that value deliberately and the route's setting must not win over it.
    """

    max_tokens: int
    temperature: float | None
    thinking_enabled: bool | None
    runtime_setting_sources: Mapping[str, str]


@dataclass(frozen=True)
class SettingsLayer:
    """A group of settings, both as they are sent and as they are reported.

    Sending and reporting are two views of one decision, so they live together:
    a layer that is dropped from the request disappears from the report in the
    same move, and neither view can quietly fall out of step with the other.
    """

    kwargs: Mapping[str, Any]
    reported: ActualRuntimeSettings


@dataclass(frozen=True)
class CallSettings:
    """One call's request, split by what losing each part would cost."""

    call: SettingsLayer
    preferences: SettingsLayer
    tools: list[dict[str, object]] | None
    tool_choice: str | None

    def build_kwargs(self) -> dict[str, Any]:
        """The arguments the route's chat model is built with.

        A setting nobody chose is left out entirely rather than sent as
        ``None``: providers read an explicit null as an instruction.
        """
        merged = {**self.call.kwargs, **self.preferences.kwargs}
        return {key: value for key, value in merged.items() if value is not None}

    @property
    def reported(self) -> ActualRuntimeSettings:
        """The settings this call actually asks for, as the answer reports them."""
        return {**self.call.reported, **self.preferences.reported}

    @property
    def preference_names(self) -> tuple[str, ...]:
        """The preferences this call carries, in the order they are sent."""
        return tuple(key for key, value in self.preferences.kwargs.items() if value is not None)

    def without_preferences(self) -> CallSettings:
        """The same call, asking for nothing but itself.

        For when a refusal has not been pinned to any one setting: nothing is
        known about which of them the route objects to, so none survives.
        """
        return replace(self, preferences=SettingsLayer(kwargs={}, reported={}))

    def without(self, names: Sequence[str]) -> CallSettings:
        """The same call, minus the named preferences and nothing else.

        Once a refusal has a name, the rest of the preferences have just been
        accepted — dropping those too would take from the caller settings
        nothing objected to.
        """
        dropped = set(names)
        return replace(
            self,
            preferences=SettingsLayer(
                kwargs={
                    key: value
                    for key, value in self.preferences.kwargs.items()
                    if key not in dropped
                },
                reported={
                    key: value
                    for key, value in self.preferences.reported.items()
                    if key.split(".", 1)[0] not in dropped
                },
            ),
        )

    def as_cheap_question(self, *, about: str | None = None) -> CallSettings:
        """The cheapest request that still asks for these settings.

        One token instead of the budget, and no tools: this asks whether the
        route takes these settings, not whether the whole call will succeed.
        Tools would make it a different, more expensive question — and one this
        answer could not be blamed for.

        Narrowed to one preference (``about``), it asks which setting a refusal
        was about: a route that answers with everything dropped and refuses with
        only this one on has named it.

        The reported view is empty on purpose — nothing answers a question, so
        there is no answer to describe, and a shape built to be refused must not
        be able to masquerade as one that was applied.
        """
        preferences = self.preferences.kwargs
        if about is not None:
            preferences = {key: value for key, value in preferences.items() if key == about}
        return replace(
            self,
            call=SettingsLayer(kwargs={**self.call.kwargs, "max_tokens": 1}, reported={}),
            preferences=SettingsLayer(kwargs=preferences, reported={}),
            tools=None,
            tool_choice=None,
        )


def compose_call_settings(
    route: ResolvedRoute,
    *,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
    budget: int,
    tools: list[dict[str, object]] | None,
    tool_choice: str | None,
) -> CallSettings:
    """Settle every setting for one call against one route."""
    asked = _asked_preferences(route, defaults, call_kwargs)
    sent, adjustments = _fit_to_route(route, asked)
    return CallSettings(
        call=_call_layer(route, defaults, call_kwargs, budget),
        preferences=SettingsLayer(
            kwargs=sent,
            reported=_with_adjustments(
                _preference_report(route, defaults, call_kwargs, sent),
                adjustments,
            ),
        ),
        tools=tools,
        tool_choice=tool_choice or _effective_text(route, "tool_choice"),
    )


# The setting each request keyword argument carries. A bound belongs to the
# setting under its registry name; the keyword is only how one request spells it.
_SETTING_OF_KWARG: Mapping[str, str] = {
    "temperature": "temperature",
    "top_p": "top_p",
    "reasoning_effort": "reasoning.effort",
    "thinking_budget_tokens": "reasoning.budget_tokens",
}

# The same correspondence read the other way, for callers holding a setting name
# and needing the keyword a request spells it with. Settings whose name and
# keyword already agree are absent from both: looking one up falls through to
# itself.
KWARG_OF_SETTING: Mapping[str, str] = {
    **{setting: keyword for keyword, setting in _SETTING_OF_KWARG.items()},
    "max_output_tokens": "max_tokens",
    "reasoning.enabled": "reasoning",
}


def _asked_preferences(
    route: ResolvedRoute,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Every preference this call would like, before any route says what it takes."""
    return {
        "temperature": _runtime_temperature(
            route,
            defaults.temperature,
            defaults.runtime_setting_sources,
            call_kwargs.get("temperature"),
        ),
        "reasoning": _runtime_reasoning(
            route,
            defaults.thinking_enabled,
            defaults.runtime_setting_sources,
            call_kwargs.get("reasoning"),
            has_kwarg="reasoning" in call_kwargs,
        ),
        "reasoning_effort": _effective_text(route, "reasoning.effort"),
        "thinking_budget_tokens": _optional_int_kwarg(
            call_kwargs.get("thinking_budget_tokens"),
            _effective_optional_int(route, "reasoning.budget_tokens"),
        ),
        "top_p": _effective_optional_float(route, "top_p"),
        "seed": _effective_optional_int(route, "seed"),
        "stop_sequences": _effective_string_list(route, "stop_sequences"),
        "parallel_tool_calls": _effective_optional_bool(route, "parallel_tool_calls"),
    }


def _fit_to_route(
    route: ResolvedRoute,
    asked: Mapping[str, Any],
) -> tuple[dict[str, Any], ActualRuntimeSettings]:
    """The preferences as this route will take them, and which ones had to move.

    An adjustment that goes unrecorded is the same silence this whole design
    exists to remove: the call would succeed on a value nobody chose.
    """
    sent: dict[str, Any] = {}
    adjustments: ActualRuntimeSettings = {}
    for keyword, value in asked.items():
        setting = _SETTING_OF_KWARG.get(keyword)
        fitted = value if setting is None else fit(value, bounds_for(route, setting))
        sent[keyword] = fitted
        if setting is not None and fitted != value:
            adjustments[setting] = {"asked": value}
    return sent, adjustments


def _with_adjustments(
    reported: ActualRuntimeSettings,
    adjustments: ActualRuntimeSettings,
) -> ActualRuntimeSettings:
    """The report, with each adjusted setting also saying what was asked for."""
    merged = dict(reported)
    for setting, adjustment in adjustments.items():
        merged[setting] = {**merged.get(setting, {}), **adjustment}
    return merged


def _call_layer(
    route: ResolvedRoute,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
    budget: int,
) -> SettingsLayer:
    """The part of the request that is the call itself, and cannot be dropped."""
    reported: dict[str, object] = {
        "value": budget,
        "source": _runtime_source(
            route,
            "max_output_tokens",
            defaults.runtime_setting_sources,
            has_kwarg=call_kwargs.get("max_tokens") is not None,
        ),
    }
    cap = budget_cap(route)
    asked = _asked_budget(route, defaults, call_kwargs)
    if cap is not None and asked > cap:
        reported["asked"] = asked
    return SettingsLayer(
        kwargs={
            "max_tokens": budget,
            "structured_output": _effective_structured_output(route),
            "call_method_id": route.call_method_id,
            "request_mapper_id": route.request_mapper_id,
        },
        reported={"max_output_tokens": reported},
    )


def _preference_report(
    route: ResolvedRoute,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
    sent: Mapping[str, Any],
) -> ActualRuntimeSettings:
    """What the answer says this call asked its provider to do."""
    return {
        "temperature": {
            "authored_value": sent["temperature"],
            "provider_value": provider_temperature_from_authored(sent["temperature"], route),
            "source": _runtime_source(
                route,
                "temperature",
                defaults.runtime_setting_sources,
                has_kwarg=call_kwargs.get("temperature") is not None,
            ),
            "protocol": route.protocol,
        },
        "reasoning.enabled": {
            "value": sent["reasoning"],
            "source": _runtime_source(
                route,
                "reasoning.enabled",
                defaults.runtime_setting_sources,
                has_kwarg="reasoning" in call_kwargs,
            ),
        },
    }


def initial_budget(
    route: ResolvedRoute,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
) -> int:
    """The output token budget a call starts on, before any escalation.

    Bounded by the same ceiling escalation obeys: a limit that only holds on
    the way up is a limit the opening request can walk straight past.
    """
    asked = _asked_budget(route, defaults, call_kwargs)
    return int(fit(asked, bounds_for(route, "max_output_tokens")))


def _asked_budget(
    route: ResolvedRoute,
    defaults: ModelDefaults,
    call_kwargs: Mapping[str, Any],
) -> int:
    kwarg_value = call_kwargs.get("max_tokens")
    if kwarg_value is not None:
        return token_budget(kwarg_value, defaults.max_tokens)
    if defaults.runtime_setting_sources.get("max_output_tokens") == "call_override":
        return defaults.max_tokens
    return _effective_int(route, "max_output_tokens", defaults.max_tokens)


def budget_cap(route: ResolvedRoute) -> int | None:
    """The most output tokens this route's model can be asked for, if it says."""
    capability = route.capabilities.get("max_output_tokens")
    value = getattr(capability, "value", None)
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


def effective_runtime_settings(route: ResolvedRoute) -> dict[str, dict[str, object]]:
    """The route's settled runtime settings, as the answer reports them."""
    return {
        key: setting.model_dump(mode="json")
        for key, setting in route.effective_runtime_settings.items()
    }


def _runtime_source(
    route: ResolvedRoute,
    key: str,
    runtime_setting_sources: Mapping[str, str],
    *,
    has_kwarg: bool,
) -> str:
    if has_kwarg:
        return "call_override"
    source = runtime_setting_sources.get(key)
    if source:
        return source
    setting = route.effective_runtime_settings.get(key)
    if setting is not None and setting.source:
        return str(setting.source)
    return "model_default"


def _runtime_temperature(
    route: ResolvedRoute,
    model_temperature: float | None,
    runtime_setting_sources: Mapping[str, str],
    kwarg_value: object,
) -> float | None:
    if kwarg_value is not None:
        return _optional_float_kwarg(kwarg_value, model_temperature)
    if runtime_setting_sources.get("temperature") == "call_override":
        return model_temperature
    return _effective_optional_float(route, "temperature")


def _runtime_reasoning(
    route: ResolvedRoute,
    model_thinking_enabled: bool | None,
    runtime_setting_sources: Mapping[str, str],
    kwarg_value: object,
    *,
    has_kwarg: bool,
) -> bool:
    if has_kwarg:
        return _bool_kwarg(kwarg_value, False)
    if runtime_setting_sources.get("reasoning.enabled") == "call_override":
        return bool(model_thinking_enabled)
    return _effective_bool(route, "reasoning.enabled", False)


def _effective_bool(route: ResolvedRoute, key: str, default: bool) -> bool:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, bool) else default


def _effective_int(route: ResolvedRoute, key: str, default: int) -> int:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return int(value) if isinstance(value, int | float) and value > 0 else default


def _effective_optional_int(route: ResolvedRoute, key: str) -> int | None:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return int(value) if isinstance(value, int | float) and value > 0 else None


def _effective_optional_float(route: ResolvedRoute, key: str) -> float | None:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, int | float) else None


def _effective_optional_bool(route: ResolvedRoute, key: str) -> bool | None:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, bool) else None


def _effective_text(route: ResolvedRoute, key: str) -> str | None:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    return value if isinstance(value, str) and value else None


def _effective_string_list(route: ResolvedRoute, key: str) -> list[str] | None:
    setting = route.effective_runtime_settings.get(key)
    value = setting.value if setting is not None else None
    if not isinstance(value, list):
        return None
    result = [item for item in value if isinstance(item, str)]
    return result or None


def _effective_structured_output(route: ResolvedRoute) -> dict[str, object] | None:
    mode = _effective_text(route, "structured_output.mode")
    if mode is None or mode == "none":
        return None
    result: dict[str, object] = {"mode": mode}
    schema_setting = route.effective_runtime_settings.get("structured_output.json_schema")
    if schema_setting is not None and isinstance(schema_setting.value, dict):
        result["json_schema"] = schema_setting.value
    strict_setting = route.effective_runtime_settings.get("structured_output.strict")
    if strict_setting is not None and isinstance(strict_setting.value, bool):
        result["strict"] = strict_setting.value
    return result


def token_budget(value: object, default: int) -> int:
    """A caller-supplied output token budget, or the default when it is not one.

    ``True`` is an int in Python and never a budget, so booleans fall to the
    default rather than silently asking a provider for one token.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return default


def _optional_int_kwarg(value: object, default: int | None) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return default


def _optional_float_kwarg(value: object, default: float | None) -> float | None:
    if isinstance(value, bool):
        return default
    try:
        return float(value) if isinstance(value, int | float | str) else default
    except ValueError:
        return default


def _bool_kwarg(value: object, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else default
