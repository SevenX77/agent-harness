"""The report says which routes ran the run, and how their settings fared.

The trace already carries this per call, which is the right place to look when
one call misbehaved and the wrong place to look when the question is "did this
run get what it asked for". So the report converges it: one block per route,
one line per setting, and the settings that did not run as asked collected
where a reader will actually see them.

Design: docs/design/2026-08-10-runtime-settings-are-preferences-decision.md D7
"""

from __future__ import annotations

from typing import Any


def _decision(route_id: str, decision: str, **extra: Any) -> dict[str, Any]:
    return {
        "event_type": "llm_route_decision",
        "phase_name": "draft",
        "decision": decision,
        "route_id": route_id,
        "provider_model_id": route_id.split(":")[-1],
        **extra,
    }


def _settings(route_id: str, settings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "event_type": "llm_call_settings",
        "phase_name": "draft",
        "route_id": route_id,
        "provider_model_id": route_id.split(":")[-1],
        "settings": settings,
    }


def test_a_run_that_used_one_route_reports_that_route_and_its_settings() -> None:
    from app.services.run_report_routes import routes_section

    section = routes_section(
        [
            _decision("deepseek:v4-pro", "answered"),
            _settings(
                "deepseek:v4-pro",
                [
                    {"setting": "temperature", "requested": 1.4, "verdict": "sent", "reason": None},
                    {
                        "setting": "top_p",
                        "requested": 5.0,
                        "verdict": "adjusted",
                        "reason": "sent as 1.0",
                    },
                ],
            ),
        ]
    )

    assert "## Routes" in section
    assert "`deepseek:v4-pro`" in section
    assert "| `temperature` | 1.4 | sent | 1 |" in section
    assert "| `top_p` | 5.0 | adjusted | 1 |" in section


def test_repeated_calls_on_one_route_count_rather_than_repeat() -> None:
    """A run makes many calls; twenty identical lines say nothing twenty times."""
    from app.services.run_report_routes import routes_section

    section = routes_section(
        [
            _settings(
                "deepseek:v4-pro",
                [{"setting": "temperature", "requested": 1.4, "verdict": "sent", "reason": None}],
            )
            for _ in range(3)
        ]
    )

    assert "| `temperature` | 1.4 | sent | 3 |" in section


def test_the_settings_that_did_not_run_as_asked_are_collected_where_they_are_read() -> None:
    from app.services.run_report_routes import routes_section

    section = routes_section(
        [
            _settings(
                "deepseek:v4-pro",
                [
                    {
                        "setting": "reasoning.enabled",
                        "requested": True,
                        "verdict": "ignored",
                        "reason": "the answer contains no reasoning",
                    }
                ],
            )
        ]
    )

    assert "### Settings that did not run as asked" in section
    assert "the answer contains no reasoning" in section


def test_a_route_the_run_never_answered_on_still_says_what_happened_to_it() -> None:
    """A route that was skipped or fell over is part of how the run went."""
    from app.services.run_report_routes import routes_section

    section = routes_section(
        [
            _decision("dead:claude", "probe_failed", reason="401 unauthorized"),
            _decision("deepseek:v4-pro", "answered"),
        ]
    )

    assert "`dead:claude`" in section
    assert "probe_failed" in section


def test_a_run_that_touched_no_route_has_no_section_to_show() -> None:
    from app.services.run_report_routes import routes_section

    assert routes_section([{"event_type": "phase_start", "phase_name": "draft"}]) == ""
