"""固定角色(fixed roles):被引擎 builtin skill 硬依赖、不可删除的 LLM 角色。

真相源在 engine —— builtin skill 用 frontmatter/`<phase_config>` 的 `llm_role:`
声明它需要哪个角色(例:`md-patch` 声明 `llm_role: fast`,它是 md2json 校验失败项
的外科式修补 agent)。studio **经 EngineAdapter 边界**读取这个引擎事实
(`app.core.adapters.engine.required_builtin_roles`),业务层不直接 import SDK
(模块边界:见 test_productization_import_boundary_red);加一个带新 `llm_role`
的 builtin skill,它自动成为固定角色,不漂移。

固定角色不可删除、不可改名:删了/改名引擎的 md2json 修补 / builtin subagent 就跑不起来。
首次缺失时由 `runtime_truth_init` 自动补上 —— 补的不是空槽,而是`_RECOMMENDED_MODELS`
里为该角色策划的推荐模型的**全部已配置 endpoint**(让用户自己在设置页删不想要的),
因为这类角色专供引擎内部子任务用,不该让用户从空白开始摸索该配什么模型。
"""

from __future__ import annotations

from functools import lru_cache

from app.core.adapters.engine import required_builtin_roles as _engine_required_builtin_roles
from app.models.llm_config import (
    LLMCredentialsFile,
    ProviderRoute,
    RoleEntry,
    RoleModelGroup,
    RoleProviderModel,
)
from app.services.llm_model_groups import normalize_model_group_key, project_model_group_identity

# (canonical_id, display_name) 顺序即角色内的推荐优先级(第一个排第一)。
# 这是产品策划的推荐,引擎/凭证目录里推导不出来,只能人工维护。
_RECOMMENDED_MODELS: dict[str, tuple[tuple[str, str], ...]] = {
    "fast": (
        ("claude-haiku-4.5", "Claude Haiku 4.5"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
    ),
}

_ROLE_DESCRIPTIONS: dict[str, str] = {
    "fast": (
        "引擎内部子任务固定使用的角色(例如 md-patch 对 md2json 校验失败项做外科式修补),"
        "追求快速响应,建议配置小/快模型:Claude Haiku 4.5、DeepSeek V4 Flash。"
    ),
}


@lru_cache(maxsize=1)
def required_builtin_roles() -> frozenset[str]:
    """引擎 builtin skill 硬依赖、不可删除的角色名集合(经 EngineAdapter 从引擎读取)。"""

    return _engine_required_builtin_roles()


def is_fixed_role(role_name: str) -> bool:
    return role_name in required_builtin_roles()


def recommended_models_for_role(role_name: str) -> tuple[str, ...]:
    """该固定角色推荐配置的模型 canonical_id,按建议优先级排序;非固定角色返回空。"""

    return tuple(canonical_id for canonical_id, _display_name in _RECOMMENDED_MODELS.get(role_name, ()))


def recommended_model_display_name(role_name: str, canonical_id: str) -> str:
    """推荐模型的人类可读展示名;查不到就原样返回 canonical_id。"""

    for spec_canonical_id, display_name in _RECOMMENDED_MODELS.get(role_name, ()):
        if spec_canonical_id == canonical_id:
            return display_name
    return canonical_id


def role_description(role_name: str) -> str:
    """人类可读的说明:这个固定角色是干嘛的、建议用什么模型。"""

    return _ROLE_DESCRIPTIONS.get(role_name, "")


def default_role_entry(role_name: str, credentials: LLMCredentialsFile) -> RoleEntry:
    """为一个(首次出现的)固定角色生成默认配置:推荐模型的**全部已配置 endpoint**都
    加进对应 Model Group,让用户自己判断删,而不是空槽。没有任何已配置 endpoint 的推荐
    模型直接跳过(不生成空 Model Group)。"""

    groups = _model_groups_for_recommended_models(_RECOMMENDED_MODELS.get(role_name, ()), credentials)
    role = RoleEntry(role_kind="graph_agent", model_groups=groups)
    if not groups:
        return role
    return _materialize(role, credentials)


def missing_recommended_models(
    role_name: str,
    role: RoleEntry | None,
    credentials: LLMCredentialsFile,
) -> list[str]:
    """该固定角色目前缺了哪些推荐模型(按 canonical_id 分组身份匹配,不是按字符串比对
    canonical_id 字面量 —— 用户后续从 Available Models 手动拖入的路由,canonical_id
    字面量可能跟种子生成的不同,但分组身份相同就算满足)。"""

    recommended = recommended_models_for_role(role_name)
    if not recommended:
        return []
    have_keys: set[str] = set()
    for group in (role.model_groups if role else []):
        for provider_model in group.provider_models:
            route = credentials.provider_routes.get(provider_model.route_id)
            if route is None:
                continue
            endpoint = credentials.provider_endpoints.get(route.endpoint_id)
            if endpoint is None:
                continue
            have_keys.add(project_model_group_identity(route=route, endpoint=endpoint).key)
    return [
        canonical_id
        for canonical_id in recommended
        if normalize_model_group_key(canonical_id) not in have_keys
    ]


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
    for canonical_id, display_name in model_specs:
        routes = routes_by_key.get(normalize_model_group_key(canonical_id))
        if not routes:
            continue
        ordered_routes = sorted(routes, key=lambda route: _route_preference_rank(route, credentials))
        groups.append(
            RoleModelGroup(
                canonical_id=canonical_id,
                display_name=display_name,
                provider_models=[RoleProviderModel(route_id=route.route_id) for route in ordered_routes],
            )
        )
    return groups


def _route_preference_rank(route: ProviderRoute, credentials: LLMCredentialsFile) -> tuple[int, str]:
    endpoint = credentials.provider_endpoints.get(route.endpoint_id)
    provider_kind = endpoint.provider_kind if endpoint else "third_party"
    kind_rank = 0 if provider_kind == "official" else 1 if provider_kind == "custom" else 2
    return (kind_rank, route.route_id)


def _materialize(role: RoleEntry, credentials: LLMCredentialsFile) -> RoleEntry:
    from app.services.llm_health_store import SqliteLlmHealthStore
    from app.services.llm_paths import credentials_path
    from app.services.llm_role_materializer import materialize_role

    health_store = SqliteLlmHealthStore(credentials_path().with_name("llm_health.sqlite"))
    return materialize_role(role, credentials, health_store)
