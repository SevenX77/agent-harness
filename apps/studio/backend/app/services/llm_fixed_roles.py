"""Fixed LLM roles that must always exist in Studio runtime truth.

Engine-required builtin role names still come from the engine adapter. Studio
product defaults, including Copilot fixed roles and recommended model groups,
are runtime config in ``app/data/llm_fixed_roles.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
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

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "llm_fixed_roles.json"


@dataclass(frozen=True)
class RecommendedModelSpec:
    canonical_id: str
    display_name: str


@dataclass(frozen=True)
class FixedRoleSpec:
    role_kind: Literal["graph_agent", "copilot"]
    recommended_models: tuple[RecommendedModelSpec, ...]


@dataclass(frozen=True)
class StudioFixedRoleConfig:
    roles: dict[str, FixedRoleSpec]


@lru_cache(maxsize=1)
def studio_fixed_role_config() -> StudioFixedRoleConfig:
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    roles_raw = raw.get("roles")
    if not isinstance(roles_raw, dict):
        raise ValueError("llm_fixed_roles.json must contain a roles object")

    roles: dict[str, FixedRoleSpec] = {}
    for role_name, role_raw in roles_raw.items():
        if not isinstance(role_name, str) or not isinstance(role_raw, dict):
            raise ValueError("fixed role entries must be named objects")
        role_kind = role_raw.get("role_kind")
        if role_kind not in ("graph_agent", "copilot"):
            raise ValueError(f"{role_name}: role_kind must be graph_agent or copilot")
        models_raw = role_raw.get("recommended_models", [])
        if not isinstance(models_raw, list):
            raise ValueError(f"{role_name}: recommended_models must be a list")
        roles[role_name] = FixedRoleSpec(
            role_kind=role_kind,
            recommended_models=tuple(_recommended_model_from_raw(role_name, item) for item in models_raw),
        )
    return StudioFixedRoleConfig(roles=roles)


def _recommended_model_from_raw(role_name: str, raw: object) -> RecommendedModelSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"{role_name}: recommended model must be an object")
    canonical_id = raw.get("canonical_id")
    display_name = raw.get("display_name")
    if not isinstance(canonical_id, str) or not canonical_id:
        raise ValueError(f"{role_name}: recommended model canonical_id must be non-empty")
    if not isinstance(display_name, str) or not display_name:
        raise ValueError(f"{role_name}: recommended model display_name must be non-empty")
    return RecommendedModelSpec(canonical_id=canonical_id, display_name=display_name)


def _recommended_model_specs(role_name: str) -> tuple[RecommendedModelSpec, ...]:
    role = studio_fixed_role_config().roles.get(role_name)
    return role.recommended_models if role is not None else ()


@lru_cache(maxsize=1)
def fixed_role_names() -> frozenset[str]:
    return _engine_required_builtin_roles() | frozenset(studio_fixed_role_config().roles)


def is_fixed_role(role_name: str) -> bool:
    return role_name in fixed_role_names()


def recommended_models_for_role(role_name: str) -> tuple[str, ...]:
    return tuple(spec.canonical_id for spec in _recommended_model_specs(role_name))


def recommended_model_display_name(role_name: str, canonical_id: str) -> str:
    for spec in _recommended_model_specs(role_name):
        if spec.canonical_id == canonical_id:
            return spec.display_name
    return canonical_id


def default_role_entry(role_name: str, credentials: LLMCredentialsFile) -> RoleEntry:
    groups = _model_groups_for_recommended_models(_recommended_model_specs(role_name), credentials)
    role = RoleEntry(role_kind=_fixed_role_kind(role_name), model_groups=groups)
    if not groups:
        return role
    return _materialize(role, credentials)


def missing_recommended_models(
    role_name: str,
    role: RoleEntry | None,
    credentials: LLMCredentialsFile,
) -> list[str]:
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
            spec for spec in _recommended_model_specs(role_name) if spec.canonical_id in missing_canonical
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
    role = studio_fixed_role_config().roles.get(role_name)
    return role.role_kind if role is not None else "graph_agent"


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
    rec_order: dict[str, int] = {}
    for index, spec in enumerate(_recommended_model_specs(role_name)):
        rec_order.setdefault(normalize_model_group_key(spec.canonical_id), index)
        rec_order.setdefault(normalize_model_group_key(spec.display_name), index)

    def sort_key(group: RoleModelGroup) -> tuple[int, int]:
        for candidate in (group.canonical_id, group.display_name):
            rank = rec_order.get(normalize_model_group_key(candidate))
            if rank is not None:
                return (0, rank)
        return (1, 0)

    return sorted(groups, key=sort_key)


def _model_groups_for_recommended_models(
    model_specs: tuple[RecommendedModelSpec, ...],
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
    for spec in model_specs:
        routes = routes_by_key.get(normalize_model_group_key(spec.canonical_id))
        if not routes:
            continue
        ordered_routes = sorted(routes, key=lambda route: _route_preference_rank(route, credentials))
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
