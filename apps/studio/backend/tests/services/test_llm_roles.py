"""Roundtrip tests for ``app.services.llm_roles`` save/load.

Covers R-F22: a Copilot shell role (`role_kind='copilot'`, empty
`model_groups` + empty `fallback_chain`) created via the frontend
``removeModelGroup`` "deselect to empty card" path MUST survive a
save -> load roundtrip without being deleted or losing its `role_kind`.
"""

from __future__ import annotations

from pathlib import Path

from app.models.llm_config import RoleEntry, RolesData
from app.services.llm_roles import load_roles_file, save_roles_file


def _empty_shell_copilot_role() -> RoleEntry:
    """Construct the exact shell shape produced by ``removeModelGroup``.

    Mirrors ``CopilotTab.tsx:343`` which writes
    ``{...role, active_model: "", models: {}, fallback_chain: []}``.
    The studio backend ``RoleEntry`` schema does not expose
    ``active_model`` / ``models`` (those are FE-only legacy fields and
    are silently ignored by Pydantic strip on validate); the persisted
    fields under test are ``role_kind`` + ``fallback_chain=[]`` +
    ``model_groups=[]``.
    """
    return RoleEntry(
        role_kind="copilot",
        system_prompt_prefix="",
        model_fallback_enabled=True,
        fallback_chain=[],
        model_groups=[],
    )


def test_save_load_shell_copilot_role(tmp_path: Path) -> None:
    """R-F22: empty-shell copilot role roundtrips through save/load.

    Reproduces the exact post-``removeModelGroup`` state: the role
    exists in ``data.roles[key]`` with no group, no chain. After
    ``save_roles_file`` -> ``load_roles_file`` the role MUST still be
    present and its ``role_kind`` MUST still be ``'copilot'`` (i.e.
    ``_reject_legacy_roles`` does not nuke it and the schema does not
    coerce it back to the default ``graph_agent``).
    """
    role_key = "copilot_custom_1"
    data = RolesData(
        schema_version=3,
        roles={role_key: _empty_shell_copilot_role()},
    )
    path = tmp_path / "llm_roles.yaml"

    # save_roles_file with empty known_route_ids set; the shell role has
    # an empty chain, so no route references are made and validation
    # passes trivially.
    save_roles_file(path, data, known_route_ids=set(), known_bundle_ids=set())

    loaded = load_roles_file(path)

    # 1. role still present (not pruned by save or _reject_legacy_roles)
    assert role_key in loaded.roles, (
        f"shell copilot role {role_key!r} dropped during roundtrip; "
        f"present keys: {list(loaded.roles)}"
    )

    reloaded = loaded.roles[role_key]

    # 2. role_kind preserved (default would be 'graph_agent' -> wrong)
    assert reloaded.role_kind == "copilot", (
        f"role_kind not preserved: got {reloaded.role_kind!r}, "
        f"expected 'copilot'"
    )

    # 3. empty containers preserved
    assert reloaded.fallback_chain == []
    assert reloaded.model_groups == []

    # 4. authoring fields preserved
    assert reloaded.model_fallback_enabled is True
    assert reloaded.system_prompt_prefix == ""
