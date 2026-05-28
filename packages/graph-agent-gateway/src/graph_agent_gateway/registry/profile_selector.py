"""Verified profile selection for provider routes."""

from __future__ import annotations

from collections.abc import Iterable

from graph_agent_gateway.registry.schema import ProviderRoute, RuntimeSettings, VerifiedProfile


class ProfileSelectionError(ValueError):
    """No verified profile can satisfy the requested runtime intent."""


def select_verified_profile(
    route: ProviderRoute,
    settings: RuntimeSettings,
    *,
    required_input_modalities: Iterable[str] | None = None,
) -> VerifiedProfile | None:
    """Select the best verified profile for one route and runtime intent."""
    ready_profiles = [profile for profile in route.verified_profiles if profile.status == "ready"]
    if not ready_profiles:
        return None

    required_modalities = set(required_input_modalities or ())
    modality_profiles = [
        profile
        for profile in ready_profiles
        if required_modalities.issubset(set(profile.input_modalities))
    ]
    if not modality_profiles:
        raise ProfileSelectionError(
            f"route {route.route_id} has no verified profile for required input modalities"
        )

    reasoning_required = settings.reasoning.enabled is True
    if reasoning_required:
        reasoning_profiles = [
            profile for profile in modality_profiles if _profile_supports_reasoning(profile)
        ]
        if not reasoning_profiles:
            raise ProfileSelectionError(
                f"route {route.route_id} has no verified reasoning profile"
            )
        return _preferred_profile(reasoning_profiles)

    non_reasoning_profiles = [
        profile for profile in modality_profiles if not _profile_supports_reasoning(profile)
    ]
    if non_reasoning_profiles:
        return _preferred_profile(non_reasoning_profiles)
    return _preferred_profile(modality_profiles)


def _profile_supports_reasoning(profile: VerifiedProfile) -> bool:
    capability = profile.capability.lower()
    profile_id = profile.profile_id.lower()
    mapper = profile.request_mapper_id.lower()
    return (
        "thinking" in capability
        or "reasoning" in capability
        or "thinking" in profile_id
        or "reasoning" in profile_id
        or "thinking" in mapper
        or "reasoning" in mapper
    )


def _preferred_profile(profiles: list[VerifiedProfile]) -> VerifiedProfile:
    return sorted(
        profiles,
        key=lambda profile: (not profile.default, profile.fallback_rank, profile.profile_id),
    )[0]
