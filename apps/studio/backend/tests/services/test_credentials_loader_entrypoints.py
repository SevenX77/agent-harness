"""Red tests for unified v4->v5 credentials loading across all entrypoints (P1).

The v4->v5 in-memory upgrade must NOT be exclusive to ``load_credentials``: the
engine resolver builder reads the credentials file directly and the gateway
adapter validates credential dicts. A stored v4 file (the on-disk reality until
the next save) must upgrade through every entrypoint instead of validation-failing
into empty credentials. Fails until a shared ``validate_credentials_payload`` helper
exists and the engine loader routes through the upgrade.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_V4_CREDENTIALS: dict[str, object] = {
    "schema_version": 4,
    "provider_endpoints": {
        "openai-direct": {
            "endpoint_id": "openai-direct",
            "display_name": "OpenAI Direct",
            "protocol": "openai_compatible",
            "base_url": "https://api.example.com/v1",
        }
    },
    "provider_routes": {
        "openai-direct:gpt-5": {
            "route_id": "openai-direct:gpt-5",
            "endpoint_id": "openai-direct",
            "route_slug": "gpt-5",
            "provider_model_id": "gpt-5",
            "canonical_id": "gpt-5",
        }
    },
}


def test_validate_credentials_payload_upgrades_v4_dict() -> None:
    from app.services.llm_credentials import validate_credentials_payload

    creds = validate_credentials_payload(dict(_V4_CREDENTIALS))

    assert creds.schema_version == 5
    assert "openai-direct" in creds.provider_endpoints
    assert "openai-direct:gpt-5" in creds.provider_routes


def test_validate_credentials_payload_passes_v5_through() -> None:
    from app.services.llm_credentials import validate_credentials_payload

    v5 = {**_V4_CREDENTIALS, "schema_version": 5, "last_remote_catalog_sync": None}
    creds = validate_credentials_payload(v5)

    assert creds.schema_version == 5
    assert "openai-direct:gpt-5" in creds.provider_routes


def test_validate_credentials_payload_rejects_bare_v3_schema_version() -> None:
    # P1: the version gate must live IN the shared helper, not only in
    # load_credentials. A bare v3 dict must NOT be silently upgraded to v5.
    from app.services.llm_credentials import validate_credentials_payload

    with pytest.raises(ValueError, match="schema_version"):
        validate_credentials_payload({"schema_version": 3})


def test_validate_credentials_payload_rejects_legacy_providers_field() -> None:
    # P1: legacy provider credentials must be rejected with a clear message at the
    # shared helper (every gateway-adapter entrypoint funnels through it).
    from app.services.llm_credentials import validate_credentials_payload

    with pytest.raises(ValueError, match="schema_version|legacy"):
        validate_credentials_payload({"schema_version": 5, "providers": [{"id": "old"}]})


def test_engine_resolver_loader_upgrades_v4_disk_file(tmp_path: Path) -> None:
    # P1: the engine resolver builder must NOT swallow a v4 file into empty creds.
    from app.core.adapters.engine import _load_resolver_credentials

    path = tmp_path / "llm_credentials.json"
    path.write_text(json.dumps(_V4_CREDENTIALS), encoding="utf-8")

    creds = _load_resolver_credentials(path)

    assert creds.schema_version == 5
    assert "openai-direct" in creds.provider_endpoints  # NOT silently emptied


def test_engine_resolver_loader_missing_file_returns_empty(tmp_path: Path) -> None:
    from app.core.adapters.engine import _load_resolver_credentials

    creds = _load_resolver_credentials(tmp_path / "nonexistent.json")

    assert creds.provider_endpoints == {}
    assert creds.provider_routes == {}


def test_filter_gateway_credentials_strips_studio_only_route_fields() -> None:
    # P2: the gateway ProviderRoute is extra=forbid and does NOT know `evidence` /
    # `display_name`. Every Studio->gateway entrypoint filters these out before the
    # RegistrySnapshot; lock that the filter strips them so a future field addition
    # can't silently break resolve. (resolver "supports v5" only via filtered v5.)
    from app.core.adapters.gateway import _filter_gateway_credentials

    v5 = {
        "schema_version": 5,
        "provider_routes": {
            "openai-direct:gpt-5": {
                "route_id": "openai-direct:gpt-5",
                "endpoint_id": "openai-direct",
                "route_slug": "gpt-5",
                "provider_model_id": "gpt-5",
                "canonical_id": "gpt-5",
                "display_name": "GPT-5",
                "evidence": [
                    {"evidence_id": "x", "evidence_type": "probe", "trust_state": "probe-verified"}
                ],
            }
        },
    }

    route = _filter_gateway_credentials(v5)["provider_routes"]["openai-direct:gpt-5"]

    assert "evidence" not in route
    assert "display_name" not in route
    assert route["route_id"] == "openai-direct:gpt-5"  # real gateway fields survive


def test_engine_resolver_loader_keeps_malformed_file_fatal(tmp_path: Path) -> None:
    # P2: a malformed/corrupt credentials file must stay FATAL (matching
    # load_credentials), not be silently swallowed into empty config. Only a
    # missing file is tolerated as first-run empty.
    from app.core.adapters.engine import _load_resolver_credentials

    path = tmp_path / "llm_credentials.json"
    path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(ValueError):
        _load_resolver_credentials(path)
