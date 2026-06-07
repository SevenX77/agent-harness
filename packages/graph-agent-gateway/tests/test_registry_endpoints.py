"""Endpoint standardization and canonical endpoint_id contract tests."""

from __future__ import annotations

from graph_agent_gateway.registry.schema import Protocol


def test_standardize_mixed_provider_input_splits_urls_by_detected_protocol() -> None:
    from graph_agent_gateway.registry.endpoints import (
        ProtocolProbeResult,
        RawProviderEndpointInput,
        standardize_endpoint_candidates,
    )

    attempts: list[tuple[str, str, str]] = []
    successful = {
        ("https://openrouter.ai/api", "openai_compatible"): "openai chat ok",
        ("https://openrouter.ai/api", "anthropic_compatible"): "anthropic messages ok",
        ("https://anthropic.qnaigc.com/v1", "anthropic_compatible"): "anthropic messages ok",
    }

    def probe(url: str, protocol: Protocol, api_key: str | None) -> ProtocolProbeResult:
        attempts.append((url, protocol, api_key or ""))
        message = successful.get((url, protocol))
        return ProtocolProbeResult(
            protocol=protocol,
            ok=message is not None,
            message=message or "protocol rejected",
        )

    result = standardize_endpoint_candidates(
        RawProviderEndpointInput(
            provider_slug="openrouter",
            display_name="OpenRouter",
            urls=["https://openrouter.ai/api", "https://anthropic.qnaigc.com/v1"],
            api_key="shared-secret",
            credential_ref="provider:openrouter",
            rate_limit_bucket="openrouter",
        ),
        probe=probe,
        protocols=("openai_compatible", "anthropic_compatible"),
    )

    assert set(result.endpoint_candidates) == {
        "openrouter-anthropic",
        "openrouter-anthropic-2",
        "openrouter-openai",
    }
    assert [
        (endpoint.endpoint_id, endpoint.protocol, endpoint.base_url)
        for endpoint in result.endpoint_candidates.values()
    ] == [
        (
            "openrouter-anthropic",
            "anthropic_compatible",
            "https://anthropic.qnaigc.com",
        ),
        (
            "openrouter-anthropic-2",
            "anthropic_compatible",
            "https://openrouter.ai/api",
        ),
        (
            "openrouter-openai",
            "openai_compatible",
            "https://openrouter.ai/api",
        ),
    ]
    assert all(
        endpoint.credential_ref == "provider:openrouter"
        and endpoint.rate_limit_bucket == "openrouter"
        for endpoint in result.endpoint_candidates.values()
    )
    assert attempts == [
        ("https://anthropic.qnaigc.com/v1", "openai_compatible", "shared-secret"),
        ("https://anthropic.qnaigc.com/v1", "anthropic_compatible", "shared-secret"),
        ("https://openrouter.ai/api", "openai_compatible", "shared-secret"),
        ("https://openrouter.ai/api", "anthropic_compatible", "shared-secret"),
    ]


def test_canonical_endpoint_ids_are_stable_when_raw_url_order_changes() -> None:
    from graph_agent_gateway.registry.endpoints import (
        ProtocolProbeResult,
        RawProviderEndpointInput,
        standardize_endpoint_candidates,
    )

    def openai_only(url: str, protocol: Protocol, api_key: str | None) -> ProtocolProbeResult:
        del url, api_key
        return ProtocolProbeResult(
            protocol=protocol,
            ok=protocol == "openai_compatible",
        )

    first = standardize_endpoint_candidates(
        RawProviderEndpointInput(
            provider_slug="myco",
            display_name="MyCo",
            urls=["https://b.example/v1", "https://a.example/v1"],
        ),
        probe=openai_only,
        protocols=("openai_compatible", "anthropic_compatible"),
    )
    second = standardize_endpoint_candidates(
        RawProviderEndpointInput(
            provider_slug="myco",
            display_name="MyCo",
            urls=["https://a.example/v1", "https://b.example/v1"],
        ),
        probe=openai_only,
        protocols=("openai_compatible", "anthropic_compatible"),
    )

    first_ids_by_url = {
        endpoint.base_url: endpoint.endpoint_id
        for endpoint in first.endpoint_candidates.values()
    }
    second_ids_by_url = {
        endpoint.base_url: endpoint.endpoint_id
        for endpoint in second.endpoint_candidates.values()
    }

    assert first_ids_by_url == {
        "https://a.example/v1": "myco-openai",
        "https://b.example/v1": "myco-openai-2",
    }
    assert second_ids_by_url == first_ids_by_url


def test_canonical_endpoint_id_suffix_avoids_reserved_existing_ids() -> None:
    from graph_agent_gateway.registry.endpoints import (
        ProtocolProbeResult,
        RawProviderEndpointInput,
        standardize_endpoint_candidates,
    )

    def openai_only(url: str, protocol: Protocol, api_key: str | None) -> ProtocolProbeResult:
        del url, api_key
        return ProtocolProbeResult(protocol=protocol, ok=protocol == "openai_compatible")

    result = standardize_endpoint_candidates(
        RawProviderEndpointInput(
            provider_slug="myco",
            display_name="MyCo",
            urls=["https://a.example/v1"],
        ),
        probe=openai_only,
        protocols=("openai_compatible",),
        reserved_endpoint_ids={"myco-openai", "myco-openai-2"},
    )

    assert list(result.endpoint_candidates) == ["myco-openai-3"]
    assert result.endpoint_candidates["myco-openai-3"].metadata["canonical_source"] == {
        "provider_slug": "myco",
        "raw_url": "https://a.example/v1",
        "protocol": "openai_compatible",
    }


def test_legacy_v3_endpoint_id_helper_preserves_known_migration_ids() -> None:
    from graph_agent_gateway.registry.endpoints import legacy_v3_endpoint_id

    assert (
        legacy_v3_endpoint_id(
            {
                "id": "legacy-openrouter-uuid",
                "name": "OpenRouter",
                "base_url": "https://openrouter.ai/api/v1",
            }
        )
        == "openrouter-prod"
    )
    assert (
        legacy_v3_endpoint_id(
            {
                "id": "legacy-qiniu",
                "name": "Qiniu Anthropic",
                "base_url": "https://api.qnaigc.com/anthropic",
            }
        )
        == "qiniu-anthropic"
    )
