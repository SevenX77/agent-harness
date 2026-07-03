"""固定角色(fixed roles):不可删除、不可改名、首次缺失自动补齐的 LLM 角色。

两类来源合成一个固定集:

1. **引擎 builtin 硬依赖**(role_kind=graph_agent)—— builtin skill 用
   frontmatter/`<phase_config>` 的 `llm_role:` 声明它需要哪个角色(例:`md-patch`
   声明 `llm_role: fast`,md2json 校验失败项的外科式修补 agent)。studio **经
   EngineAdapter 边界**读取(`app.core.adapters.engine.required_builtin_roles`),
   业务层不直接 import SDK(模块边界:见 test_productization_import_boundary_red)。
2. **Studio 固定 copilot 角色**(role_kind=copilot)—— 内置编码 copilot 角色,studio
   自己定义(`_STUDIO_FIXED_ROLES`),不是引擎事实。

固定角色不可删除/改名:删了引擎的 md2json 修补 / copilot 就跑不起来。首次缺失时由
`runtime_truth_init` 自动补上;补的不是空槽,而是 `_RECOMMENDED_MODELS` 里为该角色
策划的推荐模型的**全部已配置 endpoint**(让用户自己在设置页删不想要的)。凭证还没配
时补出来的是空角色,等用户在 API Keys 页配好后,`reconcile_fixed_roles` 在凭证变更时
把缺的推荐模型组自动补进来(组级粒度:整组缺才补,已存在的组一律不动,尊重用户删过的
endpoint 选择)。说明文案(角色是干嘛的)归前端 i18n,这里只出推荐模型清单。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from app.core.adapters.engine import required_builtin_roles as _engine_required_builtin_roles
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
    RolesData,
)
from app.services.llm_model_groups import normalize_model_group_key, project_model_group_identity

# Studio 自定义的固定 copilot 角色(不是引擎 builtin)→ 它们的 role_kind。
_STUDIO_FIXED_ROLES: dict[str, Literal["copilot"]] = {
    "copilot_claude_opus_4_8": "copilot",
    "copilot_deepseek_v4_pro": "copilot",
}

# 每个固定角色推荐的模型:(canonical_id, display_name),顺序即推荐优先级(第一个排第一)。
# 产品策划的推荐,引擎/凭证目录里推导不出来,只能人工维护。
_RECOMMENDED_MODELS: dict[str, tuple[tuple[str, str], ...]] = {
    "fast": (
        ("claude-haiku-4.5", "Claude Haiku 4.5"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
    ),
    "copilot_claude_opus_4_8": (("claude-opus-4.8", "Claude Opus 4.8"),),
    "copilot_deepseek_v4_pro": (("deepseek-v4-pro", "DeepSeek V4 Pro"),),
}


@lru_cache(maxsize=1)
def fixed_role_names() -> frozenset[str]:
    """全部固定角色名 = 引擎 builtin 硬依赖 ∪ studio 固定 copilot 角色。"""

    return _engine_required_builtin_roles() | frozenset(_STUDIO_FIXED_ROLES)


def is_fixed_role(role_name: str) -> bool:
    return role_name in fixed_role_names()


def recommended_models_for_role(role_name: str) -> tuple[str, ...]:
    """该固定角色推荐配置的模型 canonical_id,按建议优先级排序;非固定角色返回空。"""

    return tuple(canonical_id for canonical_id, _display_name in _RECOMMENDED_MODELS.get(role_name, ()))


def recommended_model_display_name(role_name: str, canonical_id: str) -> str:
    """推荐模型的人类可读展示名;查不到就原样返回 canonical_id。"""

    for spec_canonical_id, display_name in _RECOMMENDED_MODELS.get(role_name, ()):
        if spec_canonical_id == canonical_id:
            return display_name
    return canonical_id


def default_role_entry(role_name: str, credentials: LLMCredentialsFile) -> RoleEntry:
    """为一个(首次出现的)固定角色生成默认配置:推荐模型的**全部已配置 endpoint**都
    加进对应 Model Group,让用户自己判断删,而不是空槽。没有任何已配置 endpoint 的推荐
    模型直接跳过(不生成空 Model Group)。role_kind 按角色归属定(copilot / graph_agent)。"""

    groups = _model_groups_for_recommended_models(_RECOMMENDED_MODELS.get(role_name, ()), credentials)
    role = RoleEntry(role_kind=_fixed_role_kind(role_name), model_groups=groups)
    if not groups:
        return role
    return _materialize(role, credentials)


def missing_recommended_models(
    role_name: str,
    role: RoleEntry | None,
    credentials: LLMCredentialsFile,
) -> list[str]:
    """该固定角色目前缺了哪些推荐模型(按分组身份匹配,不是按 canonical_id 字面量 ——
    用户后续从 Available Models 手动拖入的路由,canonical_id 字面量可能跟种子生成的
    不同,但分组身份相同就算满足)。"""

    recommended = recommended_models_for_role(role_name)
    if not recommended:
        return []
    have_keys = _role_group_identity_keys(role, credentials)
    return [
        canonical_id
        for canonical_id in recommended
        if normalize_model_group_key(canonical_id) not in have_keys
    ]


def reconcile_fixed_roles(
    roles: RolesData,
    credentials: LLMCredentialsFile,
) -> tuple[RolesData, list[str]]:
    """凭证变更后,把每个已存在的固定角色缺失的推荐模型组补进来(组级粒度:整组缺、
    且当前凭证里有可用 route 才补;已存在的推荐组一律不动,用户删过的 endpoint 不会
    被重新塞回来)。返回 (更新后的 roles, 被改动的角色名)。完全缺失的角色由
    runtime_truth_init 的首启 seed 负责,这里只补已在场但缺模型的。"""

    updated: dict[str, RoleEntry] = dict(roles.roles)
    changed: list[str] = []
    for role_name in fixed_role_names():
        role = updated.get(role_name)
        if role is None:
            continue
        missing_canonical = set(missing_recommended_models(role_name, role, credentials))
        if not missing_canonical:
            continue
        missing_specs = tuple(
            spec for spec in _RECOMMENDED_MODELS.get(role_name, ()) if spec[0] in missing_canonical
        )
        new_groups = _model_groups_for_recommended_models(missing_specs, credentials)
        if not new_groups:
            continue
        combined = _order_groups_by_recommendation(role_name, list(role.model_groups) + new_groups)
        rebuilt = role.model_copy(update={"model_groups": combined})
        updated[role_name] = _materialize(rebuilt, credentials)
        changed.append(role_name)

    if not changed:
        return roles, []
    return roles.model_copy(update={"schema_version": 3, "roles": updated}), changed


def _fixed_role_kind(role_name: str) -> Literal["graph_agent", "copilot"]:
    return _STUDIO_FIXED_ROLES.get(role_name, "graph_agent")


def _role_group_identity_keys(role: RoleEntry | None, credentials: LLMCredentialsFile) -> set[str]:
    keys: set[str] = set()
    for group in role.model_groups if role else []:
        for provider_model in group.provider_models:
            route = credentials.provider_routes.get(provider_model.route_id)
            if route is None:
                continue
            endpoint = credentials.provider_endpoints.get(route.endpoint_id)
            if endpoint is None:
                continue
            keys.add(project_model_group_identity(route=route, endpoint=endpoint).key)
    return keys


def _order_groups_by_recommendation(
    role_name: str,
    groups: list[RoleModelGroup],
) -> list[RoleModelGroup]:
    """推荐模型组按推荐优先级排前面(fast: Haiku 先、DeepSeek 后),用户自定义的组
    保持原相对顺序排在后面。组的 canonical_id 是 registry 代表路由的(可能带发布快照),
    所以匹配推荐优先级要同时看 canonical 和 display 的归一 key。"""

    rec_order: dict[str, int] = {}
    for index, (canonical_id, display_name) in enumerate(_RECOMMENDED_MODELS.get(role_name, ())):
        rec_order.setdefault(normalize_model_group_key(canonical_id), index)
        rec_order.setdefault(normalize_model_group_key(display_name), index)

    def sort_key(group: RoleModelGroup) -> tuple[int, int]:
        for candidate in (group.canonical_id, group.display_name):
            rank = rec_order.get(normalize_model_group_key(candidate))
            if rank is not None:
                return (0, rank)
        return (1, 0)

    return sorted(groups, key=sort_key)


def _model_groups_for_recommended_models(
    model_specs: tuple[tuple[str, str], ...],
    credentials: LLMCredentialsFile,
) -> list[RoleModelGroup]:
    routes_by_key: dict[str, list[ProviderRoute]] = {}
    for route in credentials.provider_routes.values():
        endpoint = credentials.provider_endpoints.get(route.endpoint_id)
        if endpoint is None:
            continue
        key = project_model_group_identity(route=route, endpoint=endpoint).key
        routes_by_key.setdefault(key, []).append(route)

    groups: list[RoleModelGroup] = []
    for canonical_id, _spec_display_name in model_specs:
        routes = routes_by_key.get(normalize_model_group_key(canonical_id))
        if not routes:
            continue
        ordered_routes = sorted(routes, key=lambda route: _route_preference_rank(route, credentials))
        # 用 registry 会给这组挑的**代表路由**的 canonical_id / 展示名(而不是手写的推荐字面量),
        # 这样种子出的 Model Group 和「从 Available Models 拖进来」完全一致 —— 否则前端
        # data.models(按 registry canonical 建索引)里查不到这个组,pruneInvalidRoleProviders
        # 会把它当"未知模型"整组剪掉(实测:haiku 用字面量 canonical 会被剪、deepseek 恰好
        # 字面量==registry canonical 才幸存)。
        representative = ordered_routes[0]
        representative_endpoint = credentials.provider_endpoints.get(representative.endpoint_id)
        group_canonical = representative.canonical_id or representative.route_slug
        group_display = (
            project_model_group_identity(route=representative, endpoint=representative_endpoint).display_name
            if representative_endpoint is not None
            else group_canonical
        )
        groups.append(
            RoleModelGroup(
                canonical_id=group_canonical,
                display_name=group_display,
                provider_models=[RoleProviderModel(route_id=route.route_id) for route in ordered_routes],
            )
        )
    return groups


def _route_preference_rank(
    route: ProviderRoute,
    credentials: LLMCredentialsFile,
) -> tuple[int, int, int, str, str]:
    """与 registry 的 llm.py `_route_preference_rank` 对齐,确保种子挑的代表路由 = registry
    给同一组挑的代表路由(否则组 canonical 对不上,见上)。official 优先、无斜杠模型名优先、
    canonical 短的优先,再按字典序 / route_id 稳定定序。"""
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    provider_kind = endpoint.provider_kind if endpoint else "third_party"
    kind_rank = 0 if provider_kind == "official" else 1 if provider_kind == "custom" else 2
    canonical = route.canonical_id or route.route_slug
    return (
        kind_rank,
        1 if "/" in route.provider_model_id else 0,
        len(canonical),
        canonical,
        route.route_id,
    )


def _materialize(role: RoleEntry, credentials: LLMCredentialsFile) -> RoleEntry:
    from app.services.llm_health_store import SqliteLlmHealthStore
    from app.services.llm_paths import credentials_path
    from app.services.llm_role_materializer import materialize_role

    health_store = SqliteLlmHealthStore(credentials_path().with_name("llm_health.sqlite"))
    return materialize_role(role, credentials, health_store)
