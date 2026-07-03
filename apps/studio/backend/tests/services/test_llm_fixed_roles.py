"""固定角色:引擎 builtin 硬依赖、不可删除、缺失自动补槽(带推荐模型的全部 endpoint)。"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RoleEntry,
    RolesData,
)
from app.services.llm_credentials import credentials_path, save_credentials
from app.services.llm_fixed_roles import (
    default_role_entry,
    is_fixed_role,
    missing_recommended_models,
    recommended_models_for_role,
    required_builtin_roles,
    role_description,
)
from app.services.llm_paths import roles_path
from app.services.llm_roles import load_roles_file, save_roles_file
from fastapi.testclient import TestClient


def _haiku_deepseek_credentials() -> LLMCredentialsFile:
    """Two haiku routes (one official, one third-party) + two deepseek-v4-flash routes."""
    return LLMCredentialsFile(
        provider_endpoints={
            "anthropic-official": ProviderEndpoint(
                endpoint_id="anthropic-official",
                display_name="Anthropic",
                protocol="anthropic_compatible",
                base_url="https://api.anthropic.com",
                api_key="k",
                provider_kind="official",
            ),
            "wavespeed": ProviderEndpoint(
                endpoint_id="wavespeed",
                display_name="Wavespeed",
                protocol="openai_compatible",
                base_url="https://wavespeed.example/v1",
                api_key="k",
                provider_kind="third_party",
            ),
            "deepseek-official": ProviderEndpoint(
                endpoint_id="deepseek-official",
                display_name="DeepSeek",
                protocol="anthropic_compatible",
                base_url="https://api.deepseek.com",
                api_key="k",
                provider_kind="official",
            ),
            "ark-official": ProviderEndpoint(
                endpoint_id="ark-official",
                display_name="Ark",
                protocol="ark_runtime",
                base_url="https://ark.example/v1",
                api_key="k",
                provider_kind="official",
            ),
        },
        provider_routes={
            "anthropic-official:claude-haiku-4-5-20251001": ProviderRoute(
                route_id="anthropic-official:claude-haiku-4-5-20251001",
                endpoint_id="anthropic-official",
                route_slug="claude-haiku-4-5-20251001",
                provider_model_id="claude-haiku-4-5-20251001",
                canonical_id="claude-haiku-4-5-20251001",
            ),
            "wavespeed:anthropic.claude-haiku-4.5": ProviderRoute(
                route_id="wavespeed:anthropic.claude-haiku-4.5",
                endpoint_id="wavespeed",
                route_slug="anthropic.claude-haiku-4.5",
                provider_model_id="anthropic/claude-haiku-4.5",
                canonical_id="anthropic.claude-haiku-4.5",
            ),
            "deepseek-official:deepseek-v4-flash": ProviderRoute(
                route_id="deepseek-official:deepseek-v4-flash",
                endpoint_id="deepseek-official",
                route_slug="deepseek-v4-flash",
                provider_model_id="deepseek-v4-flash",
                canonical_id="deepseek-v4-flash",
            ),
            "ark-official:deepseek-v4-flash-260425": ProviderRoute(
                route_id="ark-official:deepseek-v4-flash-260425",
                endpoint_id="ark-official",
                route_slug="deepseek-v4-flash-260425",
                provider_model_id="deepseek-v4-flash-260425",
                canonical_id="deepseek-v4-flash-260425",
            ),
        },
    )


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


def test_fixed_role_status_endpoint_reports_description_and_missing_models(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(_haiku_deepseek_credentials(), credentials_path())
    from app.services.runtime_truth_init import ensure_runtime_truth_sources

    ensure_runtime_truth_sources()

    resp = client.get("/api/llm/fixed-roles/fast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_models"] == [
        {"canonical_id": "claude-haiku-4.5", "display_name": "Claude Haiku 4.5"},
        {"canonical_id": "deepseek-v4-flash", "display_name": "DeepSeek V4 Flash"},
    ]
    assert body["missing_models"] == []
    assert body["description"]


def test_fixed_role_status_endpoint_404s_for_non_fixed_role(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(monkeypatch, tmp_path, ["analyst"])

    resp = client.get("/api/llm/fixed-roles/analyst")
    assert resp.status_code == 404


def test_runtime_truth_init_seeds_missing_fixed_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 缺失的固定角色 → 启动初始化补一个空槽,让它始终在场。
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    from app.services.runtime_truth_init import ensure_runtime_truth_sources

    ensure_runtime_truth_sources()
    seeded = load_roles_file(roles_path())
    assert "fast" in seeded.roles


def test_runtime_truth_init_seeds_fast_with_all_matching_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次启动补 `fast` 时,推荐模型的**所有**已配置 endpoint 都要进去,让用户自己删,
    而不是空槽。"""
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(_haiku_deepseek_credentials(), credentials_path())
    from app.services.runtime_truth_init import ensure_runtime_truth_sources

    ensure_runtime_truth_sources()
    seeded = load_roles_file(roles_path())
    fast = seeded.roles["fast"]

    assert [group.canonical_id for group in fast.model_groups] == [
        "claude-haiku-4.5",
        "deepseek-v4-flash",
    ]
    haiku_group, deepseek_group = fast.model_groups
    assert {pm.route_id for pm in haiku_group.provider_models} == {
        "anthropic-official:claude-haiku-4-5-20251001",
        "wavespeed:anthropic.claude-haiku-4.5",
    }
    assert {pm.route_id for pm in deepseek_group.provider_models} == {
        "deepseek-official:deepseek-v4-flash",
        "ark-official:deepseek-v4-flash-260425",
    }
    fallback_route_ids = [entry.route_id for entry in fast.fallback_chain]
    assert set(fallback_route_ids) == {
        "anthropic-official:claude-haiku-4-5-20251001",
        "wavespeed:anthropic.claude-haiku-4.5",
        "deepseek-official:deepseek-v4-flash",
        "ark-official:deepseek-v4-flash-260425",
    }


def test_recommended_models_for_role_orders_haiku_before_deepseek() -> None:
    assert recommended_models_for_role("fast") == ("claude-haiku-4.5", "deepseek-v4-flash")
    assert recommended_models_for_role("copilot_chat") == ()


def test_role_description_explains_fast() -> None:
    description = role_description("fast")
    assert description
    assert "md" in description.lower() or "md2json" in description or "修补" in description


def test_default_role_entry_builds_ordered_groups_from_all_endpoints() -> None:
    credentials = _haiku_deepseek_credentials()
    entry = default_role_entry("fast", credentials)

    assert [group.canonical_id for group in entry.model_groups] == [
        "claude-haiku-4.5",
        "deepseek-v4-flash",
    ]
    assert len(entry.model_groups[0].provider_models) == 2
    assert len(entry.model_groups[1].provider_models) == 2
    assert entry.fallback_chain, "materialization should populate the fallback chain"


def test_default_role_entry_skips_recommended_model_with_no_configured_routes() -> None:
    credentials = LLMCredentialsFile()  # no routes configured at all
    entry = default_role_entry("fast", credentials)
    assert entry.model_groups == []
    assert entry.role_kind == "graph_agent"


def test_missing_recommended_models_reports_absent_model() -> None:
    credentials = _haiku_deepseek_credentials()
    fast_with_only_deepseek = default_role_entry("fast", credentials).model_copy(
        update={
            "model_groups": [
                group
                for group in default_role_entry("fast", credentials).model_groups
                if group.canonical_id == "deepseek-v4-flash"
            ]
        }
    )
    assert missing_recommended_models("fast", fast_with_only_deepseek, credentials) == [
        "claude-haiku-4.5",
    ]

    fully_seeded = default_role_entry("fast", credentials)
    assert missing_recommended_models("fast", fully_seeded, credentials) == []
