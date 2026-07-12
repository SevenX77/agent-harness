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

    # The ``anthropic/`` transport prefix (proxy routing marker, not model identity)
    # is stripped so a model reached via a proxy groups with the official route.
    assert route_slug("anthropic/claude_opus 4.7") == "claude-opus-4.7"
    assert stable_route_id(
        protocol="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        provider_model_id="anthropic/claude_opus 4.7",
    ) == f"{endpoint_id}:claude-opus-4.7"


def test_route_slug_strips_known_transport_prefix_but_keeps_model_identity() -> None:
    # The known ``anthropic/`` transport prefix is stripped ...
    assert route_slug("anthropic/claude-opus-4.8") == "claude-opus-4.8"
    # ... but a real variant suffix is part of the model identity and stays,
    # keeping it a distinct route/canonical from the base model.
    assert route_slug("anthropic/claude-opus-4.8-fast") == "claude-opus-4.8-fast"
    # Only the known transport prefix is stripped; other ``vendor/model`` shapes
    # keep their vendor segment (dot-joined) as identity.
    assert route_slug("deepseek/deepseek-v3") == "deepseek.deepseek-v3"
