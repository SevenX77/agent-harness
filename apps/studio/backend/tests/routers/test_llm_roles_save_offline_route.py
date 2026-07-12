"""Saving roles must be decoupled from the ACTIVE route registry.

Data-loss fix: a role may legitimately reference a route that is currently
offline (credential expired, model retired, route deleted). Rejecting the save
because the route is not in the active registry forces the frontend to silently
prune the offline group before it can persist anything else — which is exactly
the data-loss path this fix removes. Route existence is a read/materialization
concern (surfaced as a warning), not a write gate. Bundle references stay
validated because a dangling ``bundle_id`` is a structural authoring error.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RolesData,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_paths import roles_path
from app.services.llm_roles import load_roles_file


def _seed_empty_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    save_credentials(
        LLMCredentialsFile(provider_endpoints={}, provider_routes={}),
        settings_dir / "llm" / "llm_credentials.json",
    )


def _role_referencing_offline_route() -> RolesData:
    return RolesData(
        schema_version=3,
        roles={
            "analyst": RoleEntry(
                model_groups=[
                    RoleModelGroup(
                        canonical_id="anthropic.claude-opus-4.8",
                        display_name="Claude Opus 4.8",
                        provider_models=[
                            RoleProviderModel(route_id="anthropic-official:claude-opus-4-8"),
                        ],
                    )
                ],
            )
        },
    )


def test_save_persists_role_referencing_offline_route(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routers.llm import _save_roles_with_active_routes

    _seed_empty_registry(tmp_path, monkeypatch)

    # No HTTPException / InvalidRoleReference even though the referenced route is
    # absent from the (empty) active registry.
    saved = _save_roles_with_active_routes(_role_referencing_offline_route())

    # The offline route survives verbatim in the returned + on-disk truth.
    group = saved.roles["analyst"].model_groups[0]
    assert group.canonical_id == "anthropic.claude-opus-4.8"
    assert group.display_name == "Claude Opus 4.8"
    assert [pm.route_id for pm in group.provider_models] == [
        "anthropic-official:claude-opus-4-8"
    ]

    reloaded = load_roles_file(roles_path())
    reloaded_group = reloaded.roles["analyst"].model_groups[0]
    assert [pm.route_id for pm in reloaded_group.provider_models] == [
        "anthropic-official:claude-opus-4-8"
    ]
