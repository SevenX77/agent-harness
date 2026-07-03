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
    fixed_role_names,
    is_fixed_role,
    missing_recommended_models,
    recommended_models_for_role,
    reconcile_fixed_roles,
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


def _copilot_credentials() -> LLMCredentialsFile:
    """Opus 4.8 (official + third-party) + DeepSeek V4 Pro (third-party) routes."""
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
                display_name="WaveSpeed",
                protocol="openai_compatible",
                base_url="https://wavespeed.example/v1",
                api_key="k",
                provider_kind="third_party",
            ),
            "qiniu": ProviderEndpoint(
                endpoint_id="qiniu",
                display_name="Qiniu",
                protocol="anthropic_compatible",
                base_url="https://qiniu.example/v1",
                api_key="k",
                provider_kind="third_party",
            ),
        },
        provider_routes={
            "anthropic-official:claude-opus-4.8": ProviderRoute(
                route_id="anthropic-official:claude-opus-4.8",
                endpoint_id="anthropic-official",
                route_slug="claude-opus-4.8",
                provider_model_id="claude-opus-4.8",
                canonical_id="claude-opus-4.8",
            ),
            "wavespeed:anthropic.claude-opus-4.8": ProviderRoute(
                route_id="wavespeed:anthropic.claude-opus-4.8",
                endpoint_id="wavespeed",
                route_slug="anthropic.claude-opus-4.8",
                provider_model_id="anthropic/claude-opus-4.8",
                canonical_id="anthropic.claude-opus-4.8",
            ),
            "qiniu:deepseek.deepseek-v4-pro": ProviderRoute(
                route_id="qiniu:deepseek.deepseek-v4-pro",
                endpoint_id="qiniu",
                route_slug="deepseek.deepseek-v4-pro",
                provider_model_id="deepseek/deepseek-v4-pro",
                canonical_id="deepseek.deepseek-v4-pro",
            ),
        },
    )


def test_fast_is_derived_from_engine_builtin_md_patch() -> None:
    # md-patch/SKILL.md 声明 llm_role: fast → 固定集合必含 fast。
    roles = fixed_role_names()
    assert "fast" in roles
    assert is_fixed_role("fast") is True
    assert is_fixed_role("copilot_chat") is False


def test_copilot_roles_are_fixed() -> None:
    # 内置 copilot 角色也是固定角色(不可删/不可改名)。
    roles = fixed_role_names()
    assert "copilot_claude_opus_4_8" in roles
    assert "copilot_deepseek_v4_pro" in roles
    assert is_fixed_role("copilot_claude_opus_4_8") is True
    assert is_fixed_role("copilot_deepseek_v4_pro") is True


def test_copilot_default_role_entry_has_copilot_kind_and_all_endpoints() -> None:
    credentials = _copilot_credentials()
    opus = default_role_entry("copilot_claude_opus_4_8", credentials)
    assert opus.role_kind == "copilot"
    assert [group.display_name for group in opus.model_groups] == ["Claude Opus 4.8"]
    assert {pm.route_id for pm in opus.model_groups[0].provider_models} == {
        "anthropic-official:claude-opus-4.8",
        "wavespeed:anthropic.claude-opus-4.8",
    }

    deepseek = default_role_entry("copilot_deepseek_v4_pro", credentials)
    assert deepseek.role_kind == "copilot"
    assert [group.display_name for group in deepseek.model_groups] == ["DeepSeek V4 Pro"]


def test_delete_fixed_copilot_role_is_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(LLMCredentialsFile(), credentials_path())
    roles = {"copilot_deepseek_v4_pro": RoleEntry(role_kind="copilot")}
    save_roles_file(roles_path(), RolesData(roles=roles), known_route_ids=set(), known_bundle_ids=set())

    resp = client.delete("/api/llm/roles/copilot_deepseek_v4_pro")
    assert resp.status_code == 409
    assert "copilot_deepseek_v4_pro" in load_roles_file(roles_path()).roles


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


def test_fixed_role_status_endpoint_returns_recommended_models(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 说明文案归前端 i18n、缺哪个模型归前端实时算,后端只出推荐模型清单。
    _seed(monkeypatch, tmp_path, [])

    resp = client.get("/api/llm/fixed-roles/fast")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_models"] == [
        {"canonical_id": "claude-haiku-4.5", "display_name": "Claude Haiku 4.5"},
        {"canonical_id": "deepseek-v4-flash", "display_name": "DeepSeek V4 Flash"},
    ]
    assert "description" not in body
    assert "missing_models" not in body


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

    # Group canonical_id = registry 代表路由的(带发布快照);按稳定的 display_name 断言。
    assert [group.display_name for group in fast.model_groups] == [
        "Claude Haiku 4.5",
        "DeepSeek V4 Flash",
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


def test_default_role_entry_builds_ordered_groups_from_all_endpoints() -> None:
    credentials = _haiku_deepseek_credentials()
    entry = default_role_entry("fast", credentials)

    assert [group.display_name for group in entry.model_groups] == [
        "Claude Haiku 4.5",
        "DeepSeek V4 Flash",
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


def test_reconcile_fills_missing_recommended_group_when_routes_appear() -> None:
    """凭证配好后,固定角色缺的推荐模型组自动补齐(点 3:API Keys 配好 → 角色自动可用)。"""
    credentials = _haiku_deepseek_credentials()
    # 先造一个只有 deepseek(缺 haiku)的 fast 角色,模拟首启时只配了 deepseek。
    fast_missing_haiku = default_role_entry("fast", credentials).model_copy(
        update={
            "model_groups": [
                group
                for group in default_role_entry("fast", credentials).model_groups
                if group.canonical_id == "deepseek-v4-flash"
            ]
        }
    )
    roles = RolesData(schema_version=3, roles={"fast": fast_missing_haiku})

    updated, changed = reconcile_fixed_roles(roles, credentials)

    assert changed == ["fast"]
    fast = updated.roles["fast"]
    # 推荐优先级:补进来的 Haiku 排到 DeepSeek 前面(按稳定 display_name 断言)。
    assert [group.display_name for group in fast.model_groups] == [
        "Claude Haiku 4.5",
        "DeepSeek V4 Flash",
    ]
    assert missing_recommended_models("fast", fast, credentials) == []


def test_reconcile_is_noop_when_recommended_group_already_present() -> None:
    """组级粒度:推荐模型组已在(哪怕只剩一个 endpoint),reconcile 不再动它 —— 用户
    删过的 endpoint 不会被塞回来。"""
    credentials = _haiku_deepseek_credentials()
    seeded = default_role_entry("fast", credentials)
    # 用户从 haiku 组里删掉 wavespeed,只留 anthropic-official。
    trimmed_groups = []
    for group in seeded.model_groups:
        if group.display_name == "Claude Haiku 4.5":
            kept = [pm for pm in group.provider_models if "wavespeed" not in pm.route_id]
            trimmed_groups.append(group.model_copy(update={"provider_models": kept}))
        else:
            trimmed_groups.append(group)
    trimmed = seeded.model_copy(update={"model_groups": trimmed_groups})
    roles = RolesData(schema_version=3, roles={"fast": trimmed})

    updated, changed = reconcile_fixed_roles(roles, credentials)

    assert changed == []
    assert updated is roles
    # wavespeed 没被塞回来。
    haiku = next(g for g in updated.roles["fast"].model_groups if g.display_name == "Claude Haiku 4.5")
    assert all("wavespeed" not in pm.route_id for pm in haiku.provider_models)


def test_reconcile_skips_absent_roles_and_roles_without_matching_routes() -> None:
    # 完全缺失的角色不由 reconcile 负责(交给首启 seed);无匹配 route 时也不补。
    credentials = LLMCredentialsFile()  # 没有任何 route
    roles = RolesData(schema_version=3, roles={"fast": RoleEntry(role_kind="graph_agent")})

    updated, changed = reconcile_fixed_roles(roles, credentials)

    assert changed == []
    assert updated is roles


def test_upsert_endpoints_triggers_reconcile_fills_fixed_role(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """点 3 端到端:凭证里已有 haiku route,但 fast 角色缺 haiku;打 API Keys 保存端点
    的 PUT /registry/endpoints 后,reconcile 自动把 haiku 补进 fast。"""
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    save_credentials(_haiku_deepseek_credentials(), credentials_path())
    # fast 角色只有 deepseek,缺 haiku。
    fast_missing_haiku = default_role_entry("fast", _haiku_deepseek_credentials()).model_copy(
        update={
            "model_groups": [
                group
                for group in default_role_entry("fast", _haiku_deepseek_credentials()).model_groups
                if group.canonical_id == "deepseek-v4-flash"
            ]
        }
    )
    save_roles_file(
        roles_path(),
        RolesData(schema_version=3, roles={"fast": fast_missing_haiku}),
        known_route_ids=set(_haiku_deepseek_credentials().provider_routes),
        known_bundle_ids=set(),
    )
    assert missing_recommended_models(
        "fast", load_roles_file(roles_path()).roles["fast"], _haiku_deepseek_credentials()
    ) == ["claude-haiku-4.5"]

    # 保存一个(已存在的)端点 → 触发 reconcile。
    resp = client.put(
        "/api/llm/registry/endpoints",
        json={
            "provider_endpoints": {
                "anthropic-official": {
                    "endpoint_id": "anthropic-official",
                    "display_name": "Anthropic",
                    "protocol": "anthropic_compatible",
                    "base_url": "https://api.anthropic.com",
                    "api_key": "k",
                    "provider_kind": "official",
                }
            }
        },
    )
    assert resp.status_code == 200

    fast = load_roles_file(roles_path()).roles["fast"]
    assert missing_recommended_models("fast", fast, _haiku_deepseek_credentials()) == []
    assert [group.display_name for group in fast.model_groups] == [
        "Claude Haiku 4.5",
        "DeepSeek V4 Flash",
    ]
