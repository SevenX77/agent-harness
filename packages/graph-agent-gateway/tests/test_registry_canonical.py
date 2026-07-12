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


def test_transport_normalized_canonical_equals_route_slug_invariant() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model
    from graph_agent_gateway.registry.route_identity import route_slug

    result = canonicalize_model(
        endpoint_id="openrouter-prod",
        provider_model_id="anthropic/claude-opus-4.8",
    )

    assert result.canonical_id == "claude-opus-4.8"
    assert result.confidence == "transport_normalized"
    # The copilot vocab guard requires route_id suffix (route_slug) == canonical_id;
    # canonicalize must produce exactly what route_slug produces for the same input.
    assert result.canonical_id == route_slug("anthropic/claude-opus-4.8")


def test_variant_suffix_stays_a_distinct_canonical() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    base = canonicalize_model(
        endpoint_id="ep",
        provider_model_id="anthropic/claude-opus-4.8",
    )
    fast = canonicalize_model(
        endpoint_id="ep",
        provider_model_id="anthropic/claude-opus-4.8-fast",
    )

    assert fast.canonical_id == "claude-opus-4.8-fast"
    assert fast.confidence == "transport_normalized"
    assert base.canonical_id != fast.canonical_id


def test_official_and_proxy_forms_share_one_canonical() -> None:
    from graph_agent_gateway.registry.canonical import canonicalize_model

    official = canonicalize_model(endpoint_id="official", provider_model_id="claude-opus-4-8")
    proxy = canonicalize_model(endpoint_id="openrouter", provider_model_id="anthropic/claude-opus-4.8")

    assert official.canonical_id == proxy.canonical_id == "claude-opus-4.8"


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
