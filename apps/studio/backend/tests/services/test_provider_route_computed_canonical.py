"""canonical_id is derived on load, excluded from storage, and drives the vocab guard.

Persisting ``canonical_id`` let a stale on-disk value survive a canonicalization
rule change (the #500 transport-normalize fix), splitting one Opus group into two
until a re-probe rewrote the field. These tests lock the fix end to end:

* a credentials file carrying a STALE persisted canonical_id must, after
  ``load_credentials`` (zero probing), expose the FRESH derived value;
* official + proxy Opus then collapse into one canonical group;
* saving must not write ``canonical_id`` back to disk;
* the copilot flat-route transform groups by the route's DERIVED canonical, not a
  string-parse of ``route_id``, and fails fast on unknown routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_OFFICIAL_ENDPOINT_ID = "api-anthropic-com-anthropic-def7654321"
_PROXY_ENDPOINT_ID = "openrouter-anthropic-abc1234567"


def _stale_credentials_payload() -> dict[str, Any]:
    """v5 credentials with two Opus routes carrying pre-#500 stale canonical_ids."""
    return {
        "schema_version": 5,
        "last_remote_catalog_sync": None,
        "provider_endpoints": {
            _OFFICIAL_ENDPOINT_ID: {
                "endpoint_id": _OFFICIAL_ENDPOINT_ID,
                "display_name": "Anthropic Official",
                "protocol": "anthropic_compatible",
                "base_url": "https://api.anthropic.com",
            },
            _PROXY_ENDPOINT_ID: {
                "endpoint_id": _PROXY_ENDPOINT_ID,
                "display_name": "OpenRouter",
                "protocol": "anthropic_compatible",
                "base_url": "https://openrouter.ai/api",
            },
        },
        "provider_routes": {
            f"{_OFFICIAL_ENDPOINT_ID}:claude-opus-4-8": {
                "route_id": f"{_OFFICIAL_ENDPOINT_ID}:claude-opus-4-8",
                "endpoint_id": _OFFICIAL_ENDPOINT_ID,
                "route_slug": "claude-opus-4-8",
                "provider_model_id": "claude-opus-4-8",
                # Stale persisted grouping key from before the transport-normalize fix.
                "canonical_id": "anthropic.claude-opus-4-8",
            },
            f"{_PROXY_ENDPOINT_ID}:claude-opus-4.8": {
                "route_id": f"{_PROXY_ENDPOINT_ID}:claude-opus-4.8",
                "endpoint_id": _PROXY_ENDPOINT_ID,
                "route_slug": "claude-opus-4.8",
                "provider_model_id": "anthropic/claude-opus-4.8",
                "canonical_id": "anthropic.claude-opus-4.8",
            },
        },
    }


def _write_credentials(tmp_path: Path) -> Path:
    path = tmp_path / "llm_credentials.json"
    path.write_text(json.dumps(_stale_credentials_payload()), encoding="utf-8")
    return path


def test_load_credentials_rederives_stale_canonical_without_probe(tmp_path: Path) -> None:
    from app.services.llm_credentials import load_credentials

    creds = load_credentials(_write_credentials(tmp_path))

    official = creds.provider_routes[f"{_OFFICIAL_ENDPOINT_ID}:claude-opus-4-8"]
    proxy = creds.provider_routes[f"{_PROXY_ENDPOINT_ID}:claude-opus-4.8"]

    # Pure load, no probing — the stale "anthropic.claude-opus-4-8" is gone.
    assert official.canonical_id == "claude-opus-4.8"
    assert proxy.canonical_id == "claude-opus-4.8"


def test_official_and_proxy_opus_collapse_into_one_group_on_load(tmp_path: Path) -> None:
    from app.services.llm_credentials import load_credentials

    creds = load_credentials(_write_credentials(tmp_path))

    groups: dict[str, list[str]] = {}
    for route_id, route in creds.provider_routes.items():
        groups.setdefault(route.canonical_id, []).append(route_id)

    assert set(groups) == {"claude-opus-4.8"}
    assert len(groups["claude-opus-4.8"]) == 2


def test_save_credentials_does_not_persist_canonical_id(tmp_path: Path) -> None:
    from app.services.llm_credentials import load_credentials, save_credentials

    creds = load_credentials(_write_credentials(tmp_path))
    out_path = tmp_path / "out.json"
    save_credentials(creds, out_path)

    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    for route in on_disk["provider_routes"].values():
        assert "canonical_id" not in route
        assert "provider_model_id" in route  # the real persisted identity survives


def test_transform_groups_on_derived_canonical_not_route_id_suffix(tmp_path: Path) -> None:
    """A route whose route_id suffix (route_slug) is the OLD prefixed form must still
    group under its DERIVED clean canonical — the flat-route transform reads the
    computed field, never the route_id string (the decoupled contract)."""
    import pytest
    from app.services import copilot_tools
    from app.services.llm_credentials import load_credentials

    payload = _stale_credentials_payload()
    legacy_route_id = f"{_PROXY_ENDPOINT_ID}:anthropic.claude-opus-4.8"
    payload["provider_routes"][legacy_route_id] = {
        "route_id": legacy_route_id,
        "endpoint_id": _PROXY_ENDPOINT_ID,
        "route_slug": "anthropic.claude-opus-4.8",
        "provider_model_id": "anthropic/claude-opus-4.8",
    }
    path = tmp_path / "llm_credentials.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    creds = load_credentials(path)

    groups = copilot_tools._transform_fallback_chain_to_model_groups(
        [legacy_route_id], creds
    )

    assert len(groups) == 1
    # Grouped under the clean derived canonical, NOT the stale prefixed route_id suffix.
    assert groups[0].canonical_id == "claude-opus-4.8"
    assert groups[0].provider_models[0].route_id == legacy_route_id

    with pytest.raises(copilot_tools._FlatRouteInputError):
        copilot_tools._transform_fallback_chain_to_model_groups(
            ["ghost-endpoint:missing"], creds
        )


def test_transform_rejects_unknown_route(tmp_path: Path) -> None:
    import pytest
    from app.services import copilot_tools
    from app.services.llm_credentials import load_credentials

    creds = load_credentials(_write_credentials(tmp_path))

    with pytest.raises(copilot_tools._FlatRouteInputError) as excinfo:
        copilot_tools._transform_fallback_chain_to_model_groups(
            ["ghost-endpoint:missing"], creds
        )
    assert "ghost-endpoint:missing" in str(excinfo.value)
