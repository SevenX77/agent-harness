"""#51/#52 response-layer materialization for by-reference roles + delete cascade.

The gateway owns the bundle+delta overlay (materialize_role_entry). The Studio
shell's response materializer must:
  * materialize a PURE bundle-reference role (bundle_id set, no own model_groups)
    into the bundle's flat chain — it was skipped (empty chain) before.
  * on bundle delete, drop the dangling bundle_id from referencing roles so the
    role re-materializes with no chain (becomes not-fit) instead of 500-ing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ModelBundle,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RolesData,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.backends import clear_backend_caches

    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    # Pin the gateway adapter to in_process: get_backend_config() is lru_cached,
    # so a prior test that set STUDIO_GATEWAY_TRANSPORT=http_loopback could leak
    # its cached config here. Clearing re-reads the (clean) env -> in_process.
    monkeypatch.delenv("STUDIO_GATEWAY_TRANSPORT", raising=False)
    clear_backend_caches()
    credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_credentials(
        LLMCredentialsFile(
            provider_endpoints={
                "openai-direct": ProviderEndpoint(
                    endpoint_id="openai-direct",
                    display_name="OpenAI",
                    protocol="openai_compatible",
                    base_url="https://api.openai.example/v1",
                    api_key="secret",
                )
            },
            provider_routes={
                "openai-direct:gpt-5": ProviderRoute(
                    route_id="openai-direct:gpt-5",
                    endpoint_id="openai-direct",
                    route_slug="gpt-5",
                    provider_model_id="gpt-5",
                    canonical_id="gpt-5",
                    display_name="GPT-5",
                    status="verified",
                )
            },
        ),
        credentials_path,
    )
    save_roles_file(
        roles_path,
        RolesData(
            model_bundles={
                "primary": ModelBundle(
                    model_profile_id="primary",
                    display_name="Primary",
                    canonical_id="bundle:primary",
                    model_groups=[
                        RoleModelGroup(
                            canonical_id="gpt-5",
                            display_name="GPT-5",
                            provider_models=[
                                RoleProviderModel(route_id="openai-direct:gpt-5")
                            ],
                        )
                    ],
                )
            },
            roles={"graph_agent": RoleEntry(bundle_id="primary")},
        ),
        known_route_ids={"openai-direct:gpt-5"},
        known_bundle_ids={"primary"},
    )


def test_pure_reference_role_materializes_bundle_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, monkeypatch)
    from app.routers.llm import _load_roles_or_empty, _materialize_roles_for_response

    materialized = _materialize_roles_for_response(_load_roles_or_empty())

    role = materialized.roles["graph_agent"]
    assert role.bundle_id == "primary"
    assert [entry.route_id for entry in role.fallback_chain] == ["openai-direct:gpt-5"]


def test_delete_bundle_cascades_reference_off_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, monkeypatch)
    from app.routers.llm import _load_roles_or_empty, delete_model_bundle

    result = asyncio.run(delete_model_bundle("primary"))

    assert "primary" not in result.model_bundles
    # The referencing role's bundle_id is dropped (no dangling reference left).
    role = result.roles["graph_agent"]
    assert role.bundle_id is None
    assert role.fallback_chain == []
    # And it is durably persisted: a reload shows no dangling reference.
    reloaded = _load_roles_or_empty()
    assert reloaded.roles["graph_agent"].bundle_id is None
