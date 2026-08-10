"""Effort is a role-level choice, the same as temperature and thinking.

Today the only reasoning effort any route carries came from a capability probe
whose values were promoted into a verified profile — nobody chose it, nobody
can see it, and nobody can change it. Effort is the primary control providers
now offer for trading quality against cost, so it belongs where the other
generation params are chosen: on the role.

Decision: docs/design/2026-08-10-preferences-fit-the-route-decision.md D-F
"""

from __future__ import annotations

from typing import Any


def _route(**capabilities: Any) -> dict[str, Any]:
    return {
        "route_id": "deepseek-official:deepseek-v4-pro",
        "endpoint_id": "deepseek-official",
        "provider_model_id": "deepseek-v4-pro",
        "capabilities": {
            "thinking_protocol": {"value": True, "source": "provider_doc"},
            **capabilities,
        },
    }


def _report() -> dict[str, Any]:
    return {"resolved_settings": {}, "warnings": []}


def test_a_role_that_chose_an_effort_puts_it_on_the_route() -> None:
    from graph_agent_gateway.role_materialization import _apply_intent

    report = _report()
    _apply_intent(report, {"intent": {"reasoning_effort": "low"}}, None, _route(), "openai_compatible")

    assert report["resolved_settings"]["reasoning"]["effort"] == "low"


def test_a_role_that_chose_no_effort_leaves_the_provider_default_alone() -> None:
    """Every provider has its own default; writing one of ours over it is a choice
    nobody made."""
    from graph_agent_gateway.role_materialization import _apply_intent

    report = _report()
    _apply_intent(report, {"intent": {}}, None, _route(), "openai_compatible")

    assert "effort" not in report["resolved_settings"].get("reasoning", {})


def test_an_effort_the_model_does_not_sell_becomes_one_it_does() -> None:
    """The same fitting the request path does, done once at materialization so the
    settings the UI reads back are the settings that will be sent."""
    from graph_agent_gateway.role_materialization import _apply_intent

    report = _report()
    _apply_intent(
        report,
        {"intent": {"reasoning_effort": "xhigh"}},
        None,
        _route(
            reasoning_effort={
                "value": {"supported": True, "values": ["low", "high"]},
                "source": "probed_verified",
            }
        ),
        "openai_compatible",
    )

    assert report["resolved_settings"]["reasoning"]["effort"] == "high"


def test_a_route_nobody_probed_is_still_held_to_its_protocol_vocabulary() -> None:
    """Anthropic's request cannot spell ``none``; sending it costs a round trip to
    be told what the protocol already said."""
    from graph_agent_gateway.role_materialization import _apply_intent

    report = _report()
    _apply_intent(
        report,
        {"intent": {"reasoning_effort": "none"}},
        None,
        _route(),
        "anthropic_compatible",
    )

    assert report["resolved_settings"]["reasoning"]["effort"] == "low"


def test_choosing_an_effort_does_not_by_itself_turn_reasoning_on() -> None:
    """Effort says how hard, the thinking switch says whether — two questions."""
    from graph_agent_gateway.role_materialization import _apply_intent

    report = _report()
    _apply_intent(report, {"intent": {"reasoning_effort": "low"}}, None, _route(), "openai_compatible")

    assert "enabled" not in report["resolved_settings"]["reasoning"]
