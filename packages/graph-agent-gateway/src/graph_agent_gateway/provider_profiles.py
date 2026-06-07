"""Provider/model init-kwargs profiles for ChatX construction."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderProfile:
    """Declarative ChatX construction kwargs for one provider or exact model."""

    init_kwargs: Mapping[str, Any] = field(default_factory=dict)
    pre_init: Callable[[Any], Mapping[str, Any] | None] | None = None
    init_kwargs_factory: Callable[[Any], Mapping[str, Any] | None] | None = None


_DEFAULT_PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    "protocol:openai_compatible": ProviderProfile(init_kwargs={"stream_usage": True}),
    "protocol:ark_runtime": ProviderProfile(init_kwargs={"stream_usage": True}),
}
_PROVIDER_PROFILES: dict[str, ProviderProfile] = dict(_DEFAULT_PROVIDER_PROFILES)


def register_provider_profile(key: str, profile: ProviderProfile) -> None:
    """Register or additively merge one provider profile."""

    normalized_key = _normalize_key(key)
    existing = _PROVIDER_PROFILES.get(normalized_key)
    _PROVIDER_PROFILES[normalized_key] = (
        _merge_profiles(existing, profile) if existing is not None else profile
    )


def get_provider_profile(spec: str) -> ProviderProfile | None:
    """Return provider defaults merged with exact-model overrides."""

    normalized_spec = _normalize_key(spec)
    provider_key = normalized_spec.split(":", 1)[0]
    provider_profile = _PROVIDER_PROFILES.get(provider_key)
    exact_profile = _PROVIDER_PROFILES.get(normalized_spec)

    if provider_profile is None:
        return exact_profile
    if exact_profile is None or normalized_spec == provider_key:
        return provider_profile
    return _merge_profiles(provider_profile, exact_profile)


def route_provider_profile_keys(route: Any) -> tuple[str, str, str]:
    """Return profile overlay keys for a resolved route."""

    return (
        f"protocol:{route.protocol}",
        f"endpoint:{route.endpoint_id}",
        f"endpoint:{route.endpoint_id}:model:{route.provider_model_id}",
    )


def apply_provider_profile_layers(
    specs: Iterable[str],
    *,
    route: Any = None,
    **caller_kwargs: Any,
) -> dict[str, Any]:
    """Apply profile overlays in order with caller kwargs taking final precedence."""

    profile: ProviderProfile | None = None
    for spec in specs:
        layer = _PROVIDER_PROFILES.get(_normalize_key(spec))
        if layer is None:
            continue
        profile = layer if profile is None else _merge_profiles(profile, layer)
    if profile is None:
        return dict(caller_kwargs)
    return _apply_profile(profile, route=route, caller_kwargs=caller_kwargs)


def apply_provider_profile(
    spec: str,
    *,
    route: Any = None,
    **caller_kwargs: Any,
) -> dict[str, Any]:
    """Apply a profile with caller kwargs taking final precedence."""

    profile = get_provider_profile(spec)
    if profile is None:
        return dict(caller_kwargs)
    return _apply_profile(profile, route=route, caller_kwargs=caller_kwargs)


def _apply_profile(
    profile: ProviderProfile,
    *,
    route: Any = None,
    caller_kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if profile.pre_init is not None:
        pre_init_kwargs = profile.pre_init(route)
        if pre_init_kwargs:
            merged.update(dict(pre_init_kwargs))
    merged.update(dict(profile.init_kwargs))
    if profile.init_kwargs_factory is not None:
        factory_kwargs = profile.init_kwargs_factory(route)
        if factory_kwargs:
            merged.update(dict(factory_kwargs))
    merged.update(dict(caller_kwargs))
    return merged


def _merge_profiles(base: ProviderProfile, override: ProviderProfile) -> ProviderProfile:
    init_kwargs = {**dict(base.init_kwargs), **dict(override.init_kwargs)}
    return ProviderProfile(
        init_kwargs=init_kwargs,
        pre_init=override.pre_init or base.pre_init,
        init_kwargs_factory=override.init_kwargs_factory or base.init_kwargs_factory,
    )


def _normalize_key(key: str) -> str:
    return key.strip().lower()
