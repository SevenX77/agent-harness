"""Canonical model grouping tests."""

from __future__ import annotations


def test_transport_normalization_strips_known_proxy_prefix() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    result = canonicalize_model(
        endpoint_id="openrouter-prod",
        provider_model_id="anthropic/claude-sonnet-4.6",
    )

    assert result.canonical_id == "claude-sonnet-4.6"
    assert result.confidence == "transport_normalized"
    assert "display_name" not in result.model_dump()


def test_explicit_alias_can_merge_variant() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    result = canonicalize_model(
        endpoint_id="custom",
        provider_model_id="vendor/model-special",
        explicit_aliases={"vendor/model-special": "model-special"},
    )

    assert result.canonical_id == "model-special"
    assert result.confidence == "explicit_alias"


def test_canonicalize_model_uses_endpoint_scoped_explicit_aliases() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    aliases = {
        "endpoint-a:vendor/model": "alpha-model",
        "endpoint-b:vendor/model": "beta-model",
    }

    alpha = canonicalize_model(
        endpoint_id="endpoint-a",
        provider_model_id="vendor/model",
        explicit_aliases=aliases,
    )
    beta = canonicalize_model(
        endpoint_id="endpoint-b",
        provider_model_id="vendor/model",
        explicit_aliases=aliases,
    )

    assert alpha.canonical_id == "alpha-model"
    assert alpha.confidence == "explicit_alias"
    assert beta.canonical_id == "beta-model"
    assert beta.confidence == "explicit_alias"


def test_variants_remain_orphans_without_explicit_alias() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    latest = canonicalize_model(endpoint_id="x", provider_model_id="claude-latest")
    thinking = canonicalize_model(endpoint_id="x", provider_model_id="claude-thinking")

    assert latest.confidence == "orphan"
    assert thinking.confidence == "orphan"
    assert latest.canonical_id != thinking.canonical_id
