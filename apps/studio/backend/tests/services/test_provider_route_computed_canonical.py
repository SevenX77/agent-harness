"""canonical_id is derived on load, excluded from storage, and drives the vocab guard.

Persisting ``canonical_id`` let a stale on-disk value survive a canonicalization
rule change (the #500 transport-normalize fix), splitting one Opus group into two
until a re-probe rewrote the field. These tests lock the fix end to end:

* a credentials file carrying a STALE persisted canonical_id must, after
  ``load_credentials`` (zero probing), expose the FRESH derived value;
* official + proxy Opus then collapse into one canonical group;
* saving must not write ``canonical_id`` back to disk;
* the copilot vocab guard compares the route's DERIVED canonical, not a
  string-parse of ``route_id``.
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


def test_vocab_guard_matches_on_derived_canonical_not_route_id_suffix(tmp_path: Path) -> None:
    """route_slug suffix != derived canonical must still MATCH when the group's
    canonical_id equals the route's DERIVED canonical (the decoupled contract)."""
    from app.models.llm_config import RoleModelGroup, RoleProviderModel
    from app.services import copilot_tools
    from app.services.llm_credentials import load_credentials

    # A legacy route whose route_id suffix (route_slug) is the OLD prefixed form,
    # while its provider_model_id derives the clean canonical.
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

    good = [
        RoleModelGroup(
            canonical_id="claude-opus-4.8",
            display_name="Claude Opus 4.8",
            provider_models=[RoleProviderModel(route_id=legacy_route_id)],
        )
    ]
    assert copilot_tools._model_groups_violation(good, creds) is None

    bad = [
        RoleModelGroup(
            canonical_id="anthropic.claude-opus-4.8",  # a stale prefixed key
            display_name="Claude Opus 4.8",
            provider_models=[RoleProviderModel(route_id=legacy_route_id)],
        )
    ]
    assert copilot_tools._model_groups_violation(bad, creds) is not None


def test_vocab_guard_rejects_unknown_route(tmp_path: Path) -> None:
    from app.models.llm_config import RoleModelGroup, RoleProviderModel
    from app.services import copilot_tools
    from app.services.llm_credentials import load_credentials

    creds = load_credentials(_write_credentials(tmp_path))
    groups = [
        RoleModelGroup(
            canonical_id="claude-opus-4.8",
            display_name="Claude Opus 4.8",
            provider_models=[RoleProviderModel(route_id="ghost-endpoint:missing")],
        )
    ]
    assert copilot_tools._model_groups_violation(groups, creds) is not None
