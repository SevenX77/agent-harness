from __future__ import annotations

from app.models.llm_config import ProviderEndpoint, ProviderRoute
from app.services.llm_model_identity import project_model_identity


def _route(provider_model_id: str, canonical_id: str | None = None) -> ProviderRoute:
    route_slug = provider_model_id.lower().replace("/", ".").replace("_", "-")
    return ProviderRoute(
        route_id=f"provider:{route_slug}",
        endpoint_id="provider",
        route_slug=route_slug,
        provider_model_id=provider_model_id,
        canonical_id=canonical_id or route_slug,
    )


def _endpoint() -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id="provider",
        display_name="Provider",
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
    )


def test_model_identity_prefers_route_model_family_over_proxy_endpoint_brand() -> None:
    projection = project_model_identity(
        route=_route("deepseek-r1"),
        endpoint=ProviderEndpoint(
            endpoint_id="qiniu-anthropic",
            display_name="Qiniu Anthropic Proxy",
            protocol="anthropic_compatible",
            base_url="https://qiniu.example/anthropic",
        ),
    )

    assert projection.display_name == "DeepSeek R1"
    assert projection.section_label == "deepseek"


def test_model_identity_projection_preserves_versions_dates_and_brands() -> None:
    examples = {
        "claude-opus-4-7": "Claude Opus 4.7",
        "claude-opus-4-1-20250805": "Claude Opus 4.1 20250805",
        "deepseek/deepseek-v3.1-terminus-thinking": "DeepSeek V3.1 Terminus Thinking",
        "gpt-5.5": "GPT 5.5",
        "antigravity-preview-05-2026": "Antigravity Preview 05 2026",
    }

    for provider_model_id, expected_display_name in examples.items():
        projection = project_model_identity(
            route=_route(provider_model_id),
            endpoint=_endpoint(),
        )

        assert projection.display_name == expected_display_name
        assert projection.section_label
