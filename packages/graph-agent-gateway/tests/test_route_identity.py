from __future__ import annotations

from graph_agent_gateway.registry.route_identity import (
    route_slug,
    stable_endpoint_id,
    stable_route_id,
)


def test_stable_endpoint_id_is_derived_from_canonical_base_url_and_protocol() -> None:
    first = stable_endpoint_id(
        protocol="openai_compatible",
        base_url="https://llm.wavespeed.ai/v1/",
    )
    second = stable_endpoint_id(
        protocol="openai_compatible",
        base_url="https://llm.wavespeed.ai/v1",
    )
    different_protocol = stable_endpoint_id(
        protocol="anthropic_compatible",
        base_url="https://llm.wavespeed.ai/v1",
    )

    assert first == second
    assert first.startswith("llm-wavespeed-ai-v1-openai-")
    assert different_protocol.startswith("llm-wavespeed-ai-anthropic-")
    assert different_protocol != first
    assert "custom" not in first


def test_stable_route_id_uses_provider_model_slug_without_random_identity() -> None:
    endpoint_id = stable_endpoint_id(
        protocol="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
    )

    assert route_slug("anthropic/claude_opus 4.7") == "anthropic.claude-opus-4.7"
    assert stable_route_id(
        protocol="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        provider_model_id="anthropic/claude_opus 4.7",
    ) == f"{endpoint_id}:anthropic.claude-opus-4.7"
