from __future__ import annotations

import json
from pathlib import Path


def test_upsert_endpoints_persists_protocol_canonical_base_urls(tmp_path: Path) -> None:
    from app.services.llm_credentials import upsert_endpoints

    path = tmp_path / "llm_credentials.json"

    upsert_endpoints(
        {
            "wavespeed-anthropic": {
                "endpoint_id": "wavespeed-anthropic",
                "display_name": "WaveSpeed Anthropic",
                "protocol": "anthropic_compatible",
                "base_url": "https://llm.wavespeed.ai/v1/",
                "api_key": "secret",
            },
            "deepseek-anthropic": {
                "endpoint_id": "deepseek-anthropic",
                "display_name": "DeepSeek Anthropic",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.deepseek.com/v1/",
                "api_key": "secret",
            },
            "ark-runtime": {
                "endpoint_id": "ark-runtime",
                "display_name": "Ark Runtime",
                "protocol": "ark_runtime",
                "base_url": "https://ark.cn-beijing.volces.com/",
                "api_key": "secret",
            },
            "openai-compatible": {
                "endpoint_id": "openai-compatible",
                "display_name": "OpenAI Compatible",
                "protocol": "openai_compatible",
                "base_url": "https://api.openai.example/v1",
                "api_key": "secret",
            },
        },
        path=path,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    saved = payload["provider_endpoints"]
    assert saved["wavespeed-anthropic"]["base_url"] == "https://llm.wavespeed.ai"
    assert saved["deepseek-anthropic"]["base_url"] == "https://api.deepseek.com/anthropic"
    assert saved["ark-runtime"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
    assert saved["openai-compatible"]["base_url"] == "https://api.openai.example/v1"


def test_upserted_canonical_base_url_is_what_resolver_reads(tmp_path: Path) -> None:
    from app.services.llm_credentials import load_credentials, upsert_endpoints, upsert_routes
    from graph_agent_gateway.registry.resolver import resolve_role
    from graph_agent_gateway.registry.schema import RegistrySnapshot, RoleEntry, RoleRouteEntry

    path = tmp_path / "llm_credentials.json"
    upsert_endpoints(
        {
            "wavespeed-anthropic": {
                "endpoint_id": "wavespeed-anthropic",
                "display_name": "WaveSpeed Anthropic",
                "protocol": "anthropic_compatible",
                "base_url": "https://llm.wavespeed.ai/v1/",
                "api_key": "secret",
            },
        },
        path=path,
    )
    upsert_routes(
        {
            "wavespeed-anthropic:claude": {
                "route_id": "wavespeed-anthropic:claude",
                "endpoint_id": "wavespeed-anthropic",
                "route_slug": "claude",
                "provider_model_id": "claude",
                "canonical_id": "claude",
                "display_name": "Claude",
                "status": "verified",
            },
        },
        path=path,
    )

    credentials = load_credentials(path)
    snapshot = RegistrySnapshot(
        provider_endpoints=credentials.provider_endpoints,
        provider_routes=credentials.provider_routes,
        roles={
            "graph_agent": RoleEntry(
                fallback_chain=[RoleRouteEntry(route_id="wavespeed-anthropic:claude")]
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert (
        credentials.provider_endpoints["wavespeed-anthropic"].base_url
        == "https://llm.wavespeed.ai"
    )
    assert resolved.routes[0].base_url == "https://llm.wavespeed.ai"


def test_v3_migration_persists_protocol_canonical_base_url(tmp_path: Path) -> None:
    from app.services.llm_credentials import migrate_v3_credentials_to_v4

    path = tmp_path / "llm_credentials.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "providers": [
                    {
                        "id": "wavespeed-prod",
                        "name": "WaveSpeed",
                        "provider_type": "anthropic_compatible",
                        "base_url": "https://llm.wavespeed.ai/v1/",
                        "api_key": "secret",
                        "available_models": [{"id": "claude"}],
                    },
                    {
                        "id": "ark-official",
                        "name": "Ark",
                        "provider_type": "ark_runtime",
                        "base_url": "https://ark.cn-beijing.volces.com/",
                        "api_key": "secret",
                        "available_models": [{"id": "doubao"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    migrated = migrate_v3_credentials_to_v4(path)

    assert migrated.provider_endpoints["wavespeed-prod"].base_url == "https://llm.wavespeed.ai"
    assert (
        migrated.provider_endpoints["ark-official"].base_url
        == "https://ark.cn-beijing.volces.com/api/v3"
    )
