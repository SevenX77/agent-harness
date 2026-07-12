"""ProviderRoute.canonical_id is a read-time computed field, never persisted.

canonical_id is a pure function of ``provider_model_id`` (via ``canonicalize_model``).
Persisting it lets a stale on-disk value drift from the live canonicalization rule
(the transport-prefix fix in #500 is exactly such a rule change). These tests lock
that the model derives canonical_id fresh on every load, strips any stale persisted
value, still emits it in ``model_dump`` (API contract), and excludes it from storage.
"""

from __future__ import annotations

from typing import Any

from graph_agent_gateway.registry.canonical import canonicalize_model
from graph_agent_gateway.registry.schema import ProviderRoute


def _proxy_opus_payload(**overrides: Any) -> dict[str, Any]:
    """A proxy Opus route whose PERSISTED canonical_id is a stale pre-#500 value."""
    payload: dict[str, Any] = {
        "route_id": "openrouter-anthropic-abc1234567:claude-opus-4.8",
        "endpoint_id": "openrouter-anthropic-abc1234567",
        "route_slug": "claude-opus-4.8",
        "provider_model_id": "anthropic/claude-opus-4.8",
        # Stale persisted grouping key from the pre-transport-normalize era.
        "canonical_id": "anthropic.claude-opus-4.8",
    }
    payload.update(overrides)
    return payload


def test_stale_persisted_canonical_id_is_stripped_and_rederived() -> None:
    route = ProviderRoute.model_validate(_proxy_opus_payload())

    # The stale "anthropic.claude-opus-4.8" is ignored; the value is derived live.
    assert route.canonical_id == "claude-opus-4.8"
    assert (
        route.canonical_id
        == canonicalize_model(
            endpoint_id=route.endpoint_id,
            provider_model_id=route.provider_model_id,
        ).canonical_id
    )


def test_official_and_proxy_opus_share_one_canonical_group() -> None:
    proxy = ProviderRoute.model_validate(_proxy_opus_payload())
    official = ProviderRoute.model_validate(
        {
            "route_id": "api-anthropic-com-anthropic-def7654321:claude-opus-4-8",
            "endpoint_id": "api-anthropic-com-anthropic-def7654321",
            "route_slug": "claude-opus-4-8",
            "provider_model_id": "claude-opus-4-8",
        }
    )

    assert official.canonical_id == proxy.canonical_id == "claude-opus-4.8"


def test_fast_variant_does_not_merge_into_base_group() -> None:
    fast = ProviderRoute.model_validate(
        {
            "route_id": "openrouter-anthropic-abc1234567:claude-opus-4.8-fast",
            "endpoint_id": "openrouter-anthropic-abc1234567",
            "route_slug": "claude-opus-4.8-fast",
            "provider_model_id": "anthropic/claude-opus-4.8-fast",
        }
    )

    assert fast.canonical_id == "claude-opus-4.8-fast"


def test_model_dump_emits_derived_canonical_id_for_api_contract() -> None:
    route = ProviderRoute.model_validate(_proxy_opus_payload())

    dumped = route.model_dump(mode="json")

    # FastAPI responses serialize via model_dump; the derived key must stay present.
    assert dumped["canonical_id"] == "claude-opus-4.8"


def test_storage_exclude_drops_computed_canonical_id() -> None:
    route = ProviderRoute.model_validate(_proxy_opus_payload())

    stored = route.model_dump(mode="json", exclude={"canonical_id"})

    assert "canonical_id" not in stored
    assert stored["provider_model_id"] == "anthropic/claude-opus-4.8"
