"""Transport-normalized canonical grouping at the persisted route-build boundary.

Grounds the 2026-07-11 acceptance finding: the same model (Claude Opus 4.8)
reached via the official endpoint and via a proxy (openrouter/wavespeed, which
report ``anthropic/claude-opus-4.8``) must collapse to ONE canonical group so a
model_group can fall back across provider routes. The known ``anthropic/``
transport prefix is a routing marker, not model identity, and is stripped for
grouping; the raw ``provider_model_id`` used to actually call the provider is
preserved.
"""

from __future__ import annotations

from app.models.llm_config import ProviderEndpoint
from app.routers.llm import _provider_route


def _endpoint(endpoint_id: str) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        display_name=endpoint_id,
        protocol="openai_compatible",
        base_url=f"https://{endpoint_id}.example/v1",
    )


def test_provider_route_transport_normalizes_and_keeps_vocab_invariant() -> None:
    route = _provider_route(
        endpoint=_endpoint("openrouter"),
        model_id="anthropic/claude-opus-4.8",
        status="verified",
        capability_source="probed_verified",
    )

    assert route.canonical_id == "claude-opus-4.8"
    # A freshly probed route's route_id suffix (route_slug) equals its derived
    # canonical_id; the copilot flat-route transform groups on the derived value.
    assert route.route_id.partition(":")[2] == route.canonical_id
    assert route.route_slug == route.canonical_id
    # The raw id used to actually CALL the provider is preserved untouched.
    assert route.provider_model_id == "anthropic/claude-opus-4.8"


def test_official_and_proxy_routes_share_one_canonical_group() -> None:
    official = _provider_route(
        endpoint=_endpoint("official-anthropic"),
        model_id="claude-opus-4-8",
        status="verified",
        capability_source="probed_verified",
    )
    proxy = _provider_route(
        endpoint=_endpoint("openrouter"),
        model_id="anthropic/claude-opus-4.8",
        status="verified",
        capability_source="probed_verified",
    )

    # One canonical → one model_group with two provider routes (fallback).
    assert official.canonical_id == proxy.canonical_id == "claude-opus-4.8"
    # Distinct physical routes, disambiguated by their endpoint prefix.
    assert official.route_id != proxy.route_id


def test_real_variant_stays_a_distinct_canonical_group() -> None:
    base = _provider_route(
        endpoint=_endpoint("openrouter"),
        model_id="anthropic/claude-opus-4.8",
        status="verified",
        capability_source="probed_verified",
    )
    variant = _provider_route(
        endpoint=_endpoint("openrouter"),
        model_id="anthropic/claude-opus-4.8-fast",
        status="verified",
        capability_source="probed_verified",
    )

    assert variant.canonical_id == "claude-opus-4.8-fast"
    assert base.canonical_id != variant.canonical_id
    assert variant.route_id.partition(":")[2] == variant.canonical_id
