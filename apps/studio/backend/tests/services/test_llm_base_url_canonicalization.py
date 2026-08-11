from __future__ import annotations

import json
from pathlib import Path

from graph_agent_gateway.registry import stable_endpoint_id


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

    # WaveSpeed has no curated/official mapping → endpoint_id is derived from
    # the canonical (protocol, base_url) pair by stable_endpoint_id.
    wavespeed_persisted_id = stable_endpoint_id(
        protocol="anthropic_compatible", base_url="https://llm.wavespeed.ai"
    )
    assert saved[wavespeed_persisted_id]["base_url"] == "https://llm.wavespeed.ai"

    # DeepSeek's official matrix currently declares only its OpenAI-compatible
    # cell. A DeepSeek Anthropic-compatible authoring row still gets the
    # protocol-specific canonical base URL, but not a host-only official id.
    deepseek_persisted_id = stable_endpoint_id(
        protocol="anthropic_compatible", base_url="https://api.deepseek.com/anthropic"
    )
    assert saved[deepseek_persisted_id]["base_url"] == "https://api.deepseek.com/anthropic"

    # Ark runtime is declared as an official protocol cell, so the incoming
    # endpoint_id is rewritten to the curated `ark-official` id.
    assert saved["ark-official"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"

    # Generic openai-compatible endpoints also flow through stable_endpoint_id.
    openai_persisted_id = stable_endpoint_id(
        protocol="openai_compatible", base_url="https://api.openai.example/v1"
    )
    assert saved[openai_persisted_id]["base_url"] == "https://api.openai.example/v1"


def test_upsert_endpoints_keeps_ark_openai_compatible_endpoint_separate(tmp_path: Path) -> None:
    from app.services.llm_credentials import upsert_endpoints

    path = tmp_path / "llm_credentials.json"

    upsert_endpoints(
        {
            "ark-runtime": {
                "endpoint_id": "ark-runtime",
                "display_name": "Ark Runtime",
                "protocol": "ark_runtime",
                "base_url": "https://ark.cn-beijing.volces.com/",
                "api_key": "secret",
            },
            "ark-openai-official": {
                "endpoint_id": "ark-openai-official",
                "display_name": "Ark Official",
                "protocol": "openai_compatible",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "api_key": "secret",
            },
        },
        path=path,
    )

    saved = json.loads(path.read_text(encoding="utf-8"))["provider_endpoints"]

    assert saved["ark-official"]["protocol"] == "ark_runtime"
    assert saved["ark-openai-official"]["protocol"] == "openai_compatible"
    assert saved["ark-openai-official"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"


def test_upserted_canonical_base_url_is_what_resolver_reads(tmp_path: Path) -> None:
    from app.services.llm_credentials import load_credentials, upsert_endpoints, upsert_routes
    from graph_agent_gateway.registry import RegistrySnapshot, RoleEntry, RoleRouteEntry
    from graph_agent_gateway.registry.resolver import resolve_role

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

    # Routes must reference the persisted endpoint_id, not the caller-supplied one.
    persisted_endpoint_id = stable_endpoint_id(
        protocol="anthropic_compatible", base_url="https://llm.wavespeed.ai"
    )
    route_id = f"{persisted_endpoint_id}:claude"
    upsert_routes(
        {
            route_id: {
                "route_id": route_id,
                "endpoint_id": persisted_endpoint_id,
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
                fallback_chain=[RoleRouteEntry(route_id=route_id)]
            )
        },
    )

    resolved = resolve_role(snapshot, "graph_agent")

    assert (
        credentials.provider_endpoints[persisted_endpoint_id].base_url
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

    # WaveSpeed has no curated/official mapping → the v3 id is rewritten by
    # stable_endpoint_id on migration.
    wavespeed_persisted_id = stable_endpoint_id(
        protocol="anthropic_compatible", base_url="https://llm.wavespeed.ai"
    )
    assert migrated.provider_endpoints[wavespeed_persisted_id].base_url == "https://llm.wavespeed.ai"

    # Ark host is recognized as official → id is rewritten to `ark-official`
    # (matches the incoming v3 id in this fixture, but the derivation runs).
    assert (
        migrated.provider_endpoints["ark-official"].base_url
        == "https://ark.cn-beijing.volces.com/api/v3"
    )
