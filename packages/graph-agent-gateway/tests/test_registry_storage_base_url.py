"""Registry storage base URL canonicalization contract tests."""

from __future__ import annotations

from pydantic import SecretStr


def test_credential_fingerprint_uses_protocol_canonical_base_url() -> None:
    from graph_agent_gateway.registry.base_url import canonicalize_base_url
    from graph_agent_gateway.registry.schema import ProviderEndpoint
    from graph_agent_gateway.registry.storage import compute_credential_fingerprint

    raw_endpoint = ProviderEndpoint(
        endpoint_id="wavespeed-anthropic",
        protocol="anthropic_compatible",
        base_url="https://llm.wavespeed.ai/v1/",
        api_key=SecretStr("secret"),
    )
    canonical_endpoint = raw_endpoint.model_copy(
        update={
            "base_url": canonicalize_base_url(
                raw_endpoint.base_url,
                raw_endpoint.protocol,
            )
        }
    )

    assert canonical_endpoint.base_url == "https://llm.wavespeed.ai"
    assert compute_credential_fingerprint(raw_endpoint) == compute_credential_fingerprint(
        canonical_endpoint
    )
