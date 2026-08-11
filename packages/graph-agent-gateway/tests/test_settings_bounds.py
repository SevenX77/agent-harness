"""A preference is made to fit the route before it is offered to it.

Every setting has a range the route will actually take. Handing over a value
outside that range spends a round trip to learn something the route already
told us: the ceiling was in its capabilities the whole time.

So the value is fitted first — clamped to the bound, snapped to the nearest
level the model has — and only what has no known bound is offered as written,
where the refusal path from the preceding decision still catches it.

Decision: docs/design/2026-08-10-preferences-fit-the-route-decision.md
"""

from __future__ import annotations

from typing import Any

CAPABILITY_SOURCE = "provider_doc"


def _route(
    *,
    protocol: str = "openai_compatible",
    capabilities: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> Any:
    from graph_agent_gateway.registry import (
        CapabilityValue,
        EffectiveRuntimeSetting,
        ResolvedRoute,
    )

    return ResolvedRoute(
        role_name="graph_agent",
        route_id="deepseek-official:deepseek-v4-pro",
        endpoint_id="deepseek-official",
        protocol=protocol,  # type: ignore[arg-type]
        base_url="https://api.deepseek.example/v1",
        credential_ref="endpoint:deepseek-official",
        credential_fingerprint="fingerprint-a",
        provider_model_id="deepseek-v4-pro",
        canonical_id="deepseek-v4-pro",
        timeout_seconds=17,
        capabilities={
            key: CapabilityValue(value=value, source=CAPABILITY_SOURCE)
            for key, value in (capabilities or {}).items()
        },
        effective_runtime_settings={
            key: EffectiveRuntimeSetting(value=value, source="route_setting")
            for key, value in (settings or {}).items()
        },
    )


def _defaults() -> Any:
    from graph_agent_gateway.call import ModelDefaults

    return ModelDefaults(
        max_tokens=1024,
        temperature=None,
        thinking_enabled=None,
        runtime_setting_sources={},
    )


def test_a_temperature_above_the_scale_arrives_as_the_ceiling_not_above_it() -> None:
    """3.0 on a 0..2 dial means "as hot as it goes", not "past the end of it"."""
    from graph_agent_gateway.registry import provider_temperature_from_authored

    anthropic = _route(protocol="anthropic_compatible")
    openai = _route(protocol="openai_compatible")

    assert provider_temperature_from_authored(3.0, anthropic) == 1.0
    assert provider_temperature_from_authored(3.0, openai) == 2.0
    assert provider_temperature_from_authored(-1.0, openai) == 0.0


def test_the_routes_own_temperature_ceiling_wins_over_the_protocol_default() -> None:
    """A model that says its own ceiling is answering a question the protocol guessed at."""
    from graph_agent_gateway.registry import provider_temperature_from_authored

    route = _route(capabilities={"temperature": {"supported": True, "max": 1.0}})

    assert provider_temperature_from_authored(2.0, route) == 1.0
    assert provider_temperature_from_authored(1.0, route) == 0.5


def test_a_budget_over_the_models_ceiling_starts_at_the_ceiling() -> None:
    """The cap already bounded escalation; the value a call opens with obeys it too."""
    from graph_agent_gateway.call import initial_budget

    route = _route(capabilities={"max_output_tokens": 8192})

    assert initial_budget(route, _defaults(), {"max_tokens": 999_999}) == 8192
    assert initial_budget(route, _defaults(), {"max_tokens": 512}) == 512


def test_an_effort_the_model_does_not_have_becomes_the_most_it_does_below_it() -> None:
    """Asking for a level the model lacks buys its nearest level below, never above.

    Effort is spending. Rounding up quietly bills the caller for thinking they
    did not ask for, so an unsupported level steps down; only a level under
    everything the model sells steps up, to the least it sells.

    Levels the model does accept never reach here: the probe records what it
    took, so folding (DeepSeek reads ``xhigh`` as ``max``) stays the provider's
    to do.
    """
    from graph_agent_gateway.registry import bounds_for, fit

    route = _route(
        capabilities={
            "reasoning_effort": {"supported": True, "values": ["low", "high", "max"]},
        },
    )
    bounds = bounds_for(route, "reasoning.effort")

    assert fit("xhigh", bounds) == "high"
    assert fit("medium", bounds) == "low"
    assert fit("high", bounds) == "high"
    assert fit("none", bounds) == "low"


def test_a_protocol_that_documents_its_effort_levels_bounds_them_without_a_probe() -> None:
    """The level names are the protocol's, not the model's, so they need no measuring.

    Verified 2026-08-10 against the adapters that build the request:
    ``ChatAnthropic.effort`` is typed ``low|medium|high|xhigh|max`` and
    ``ChatGoogleGenerativeAI.thinking_level`` ``minimal|low|medium|high``.
    """
    from graph_agent_gateway.registry import bounds_for, fit

    anthropic = bounds_for(_route(protocol="anthropic_compatible"), "reasoning.effort")
    google = bounds_for(_route(protocol="google_genai"), "reasoning.effort")

    assert fit("minimal", anthropic) == "low"
    assert fit("max", anthropic) == "max"
    assert fit("max", google) == "high"
    assert fit("minimal", google) == "minimal"


def test_what_the_model_was_measured_to_take_wins_over_what_the_protocol_documents() -> None:
    """A measured refusal outranks a documented level the model turned out to lack."""
    from graph_agent_gateway.registry import bounds_for, fit

    route = _route(
        protocol="anthropic_compatible",
        capabilities={"reasoning_effort": {"supported": True, "values": ["low", "high"]}},
    )

    assert fit("max", bounds_for(route, "reasoning.effort")) == "high"


def test_an_effort_nobody_can_rank_is_left_for_the_provider_to_judge() -> None:
    """A word off the ladder has no "nearest" — guessing one invents a bound."""
    from graph_agent_gateway.registry import bounds_for, fit

    route = _route(
        capabilities={
            "reasoning_effort": {"supported": True, "values": ["low", "high", "max"]},
        },
    )

    assert fit("turbo", bounds_for(route, "reasoning.effort")) == "turbo"


def test_a_top_p_above_one_arrives_at_one() -> None:
    """Nucleus sampling is a share of the distribution; there is no more than all of it."""
    from graph_agent_gateway.registry import bounds_for, fit

    bounds = bounds_for(_route(), "top_p")

    assert fit(5.0, bounds) == 1.0
    assert fit(0.4, bounds) == 0.4


def test_an_adjusted_setting_reports_what_was_asked_for() -> None:
    """Fitting silently would trade one invisible failure for one invisible success."""
    from graph_agent_gateway.call import compose_call_settings, initial_budget

    route = _route(capabilities={"max_output_tokens": 8192}, settings={"top_p": 5.0})
    call_kwargs = {"max_tokens": 999_999}
    settings = compose_call_settings(
        route,
        defaults=_defaults(),
        call_kwargs=call_kwargs,
        budget=initial_budget(route, _defaults(), call_kwargs),
        tools=None,
        tool_choice=None,
    )

    assert settings.build_kwargs()["top_p"] == 1.0
    assert settings.reported["top_p"] == {
        "asked": 5.0,
        "value": 1.0,
        "source": "route_setting",
    }
    assert settings.build_kwargs()["max_tokens"] == 8192
    assert settings.reported["max_output_tokens"]["asked"] == 999_999


def test_a_setting_that_fits_reports_no_asked_for_value() -> None:
    """"Asked for" only means something when it differs from what was sent."""
    from graph_agent_gateway.call import compose_call_settings, initial_budget

    route = _route(capabilities={"max_output_tokens": 8192}, settings={"top_p": 0.4})
    call_kwargs = {"max_tokens": 512}
    settings = compose_call_settings(
        route,
        defaults=_defaults(),
        call_kwargs=call_kwargs,
        budget=initial_budget(route, _defaults(), call_kwargs),
        tools=None,
        tool_choice=None,
    )

    assert "top_p" not in settings.reported
    assert "asked" not in settings.reported["max_output_tokens"]


def test_a_setting_with_no_known_bound_is_sent_as_written() -> None:
    """Inventing a bound to clamp against is worse than not clamping."""
    from graph_agent_gateway.registry import bounds_for, fit

    bounds = bounds_for(_route(), "reasoning.effort")

    assert bounds.known is False
    assert fit("xhigh", bounds) == "xhigh"
