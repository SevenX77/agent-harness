"""固定角色:引擎 builtin 硬依赖、不可删除、缺失自动补槽。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import LLMCredentialsFile, RoleEntry, RolesData
from app.services.llm_credentials import credentials_path, save_credentials
from app.services.llm_fixed_roles import is_fixed_role, required_builtin_roles
from app.services.llm_paths import roles_path
from app.services.llm_roles import load_roles_file, save_roles_file
from fastapi.testclient import TestClient


def test_fast_is_derived_from_engine_builtin_md_patch() -> None:
    # md-patch/SKILL.md 声明 llm_role: fast → 派生集合必含 fast。
    roles = required_builtin_roles()
    assert "fast" in roles
    assert is_fixed_role("fast") is True
    assert is_fixed_role("copilot_chat") is False


def _seed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, role_names: list[str]) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(LLMCredentialsFile(), credentials_path())
    roles = {n: RoleEntry(role_kind="graph_agent") for n in role_names}
    save_roles_file(roles_path(), RolesData(roles=roles), known_route_ids=set(), known_bundle_ids=set())


def test_delete_fixed_role_is_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(monkeypatch, tmp_path, ["fast", "analyst"])

    resp = client.delete("/api/llm/roles/fast")
    assert resp.status_code == 409
    # 仍在盘上,没被删。
    assert "fast" in load_roles_file(roles_path()).roles


def test_delete_non_fixed_role_still_works(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(monkeypatch, tmp_path, ["fast", "analyst"])

    resp = client.delete("/api/llm/roles/analyst")
    assert resp.status_code == 200
    assert "analyst" not in load_roles_file(roles_path()).roles


def test_fixed_roles_endpoint_lists_fast(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(monkeypatch, tmp_path, [])

    resp = client.get("/api/llm/fixed-roles")
    assert resp.status_code == 200
    assert "fast" in resp.json()["fixed_role_names"]


def test_runtime_truth_init_seeds_missing_fixed_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 缺失的固定角色 → 启动初始化补一个空槽,让它始终在场。
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    from app.services.runtime_truth_init import ensure_runtime_truth_sources

    ensure_runtime_truth_sources()
    seeded = load_roles_file(roles_path())
    assert "fast" in seeded.roles
