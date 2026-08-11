"""What became of each setting the caller asked for.

A run that only speaks up on failure looks correct right up until someone
checks. These verdicts are the other half: for every setting a user actually
chose, one closed answer about what happened to it, including the answers that
are uncomfortable — sent but unverifiable, accepted but disregarded.

Decision: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md
(D3 the closed verdict set, D8 only what the user set)
"""

from __future__ import annotations

from typing import Any

CARRIED = {
    "temperature": "temperature",
    "max_tokens": "max_completion_tokens",
    "top_p": "top_p",
    "seed": "seed",
    "reasoning_effort": "reasoning_effort",
}


def _judge(**overrides: Any) -> dict[str, Any]:
    from graph_agent_gateway.call import judge_settings

    arguments: dict[str, Any] = {
        "reported": {},
        "carried": CARRIED,
        "refused": (),
        "reasoned": None,
    }
    arguments.update(overrides)
    return {outcome.setting: outcome for outcome in judge_settings(**arguments)}


def test_only_the_settings_a_user_chose_are_judged() -> None:
    """A default nobody picked is not a preference; reporting it buries the ones that are."""
    outcomes = _judge(
        reported={
            "top_p": {"value": 0.4, "source": "route_setting"},
            "seed": {"value": 7, "source": "profile_default"},
        },
    )

    assert set(outcomes) == {"top_p"}


def test_a_setting_this_protocol_cannot_carry_is_unsupported() -> None:
    """Nothing was sent, so nothing can have been applied, refused or ignored."""
    outcomes = _judge(
        reported={"stop_sequences": {"value": ["END"], "source": "route_setting"}},
        carried={"temperature": "temperature"},
    )

    assert outcomes["stop_sequences"].verdict == "unsupported"


def test_a_setting_the_provider_refused_is_rejected() -> None:
    outcomes = _judge(
        reported={"top_p": {"value": 5.0, "source": "route_setting"}},
        refused=("top_p",),
    )

    assert outcomes["top_p"].verdict == "rejected"


def test_a_setting_that_had_to_be_moved_is_adjusted_and_says_what_was_asked() -> None:
    outcomes = _judge(
        reported={"top_p": {"value": 1.0, "asked": 5.0, "source": "route_setting"}},
    )

    assert outcomes["top_p"].verdict == "adjusted"
    assert outcomes["top_p"].requested == 5.0


def test_reasoning_asked_for_and_seen_in_the_answer_is_applied() -> None:
    """The one setting whose effect the answer itself can testify to."""
    outcomes = _judge(
        reported={"reasoning.enabled": {"value": True, "source": "call_override"}},
        reasoned=True,
    )

    assert outcomes["reasoning.enabled"].verdict == "applied"


def test_reasoning_asked_for_and_absent_from_the_answer_is_ignored() -> None:
    """Accepted without complaint and disregarded anyway — the silent failure."""
    outcomes = _judge(
        reported={"reasoning.enabled": {"value": True, "source": "call_override"}},
        reasoned=False,
    )

    assert outcomes["reasoning.enabled"].verdict == "ignored"


def test_a_setting_the_answer_cannot_testify_about_is_sent_not_applied() -> None:
    """Silence is not evidence: calling this applied would be a claim nobody checked."""
    outcomes = _judge(
        reported={"temperature": {"authored_value": 1.4, "source": "route_setting"}},
    )

    assert outcomes["temperature"].verdict == "sent"
    assert outcomes["temperature"].requested == 1.4


def test_a_setting_known_only_by_having_been_adjusted_still_gets_a_verdict() -> None:
    """Measured 2026-08-10 against api.deepseek.com: top_p 5.0 went out as 1.0, and
    the settings event said nothing about it.

    Only settings with their own report entry carry a source. One known solely
    because it had to be moved carried none, so the "did a user choose this"
    filter dropped it — and an adjustment nobody is told about is the silence
    this whole design exists to remove.
    """
    from graph_agent_gateway.call import (
        ModelDefaults,
        compose_call_settings,
        initial_budget,
        judge_settings,
    )
    from graph_agent_gateway.registry import EffectiveRuntimeSetting, ResolvedRoute

    route = ResolvedRoute(
        role_name="graph_agent",
        route_id="deepseek-official:deepseek-v4-pro",
        endpoint_id="deepseek-official",
        protocol="openai_compatible",
        base_url="https://api.deepseek.example/v1",
        credential_ref="endpoint:deepseek-official",
        credential_fingerprint="fingerprint-a",
        provider_model_id="deepseek-v4-pro",
        canonical_id="deepseek-v4-pro",
        effective_runtime_settings={
            "top_p": EffectiveRuntimeSetting(value=5.0, source="route_setting"),
        },
    )
    defaults = ModelDefaults(
        max_tokens=1024, temperature=None, thinking_enabled=None, runtime_setting_sources={}
    )
    settings = compose_call_settings(
        route,
        defaults=defaults,
        call_kwargs={},
        budget=initial_budget(route, defaults, {}),
        tools=None,
        tool_choice=None,
    )
    outcomes = {
        outcome.setting: outcome
        for outcome in judge_settings(
            reported=settings.reported, carried=CARRIED, refused=(), reasoned=None
        )
    }

    assert settings.build_kwargs()["top_p"] == 1.0
    assert outcomes["top_p"].verdict == "adjusted"
    assert outcomes["top_p"].requested == 5.0


def test_a_source_no_resolver_can_produce_is_not_treated_as_one_that_can() -> None:
    """``EffectiveRuntimeSetting.source`` is a closed set; membership is checkable."""
    from graph_agent_gateway.call import AUTHORED_SOURCES, CALL_OVERRIDE
    from graph_agent_gateway.registry import EffectiveRuntimeSetting

    resolver_sources = set(EffectiveRuntimeSetting.model_fields["source"].annotation.__args__)

    assert AUTHORED_SOURCES - {CALL_OVERRIDE} <= resolver_sources
