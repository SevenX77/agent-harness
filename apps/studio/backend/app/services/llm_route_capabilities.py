"""Helpers for deriving route capabilities from verified invocation profiles."""

from __future__ import annotations

from graph_agent_gateway.registry.schema import VerifiedProfile

from app.models.llm_config import CapabilityValue, ProviderRoute


def route_effective_capabilities(route: ProviderRoute) -> dict[str, CapabilityValue]:
    """Return route capabilities with ready verified-profile facts applied."""
    return {
        **route.capabilities,
        **verified_profile_route_capabilities(route.verified_profiles),
    }


def route_thinking_capability(route: ProviderRoute) -> CapabilityValue | None:
    return route_effective_capabilities(route).get("thinking_protocol")


def verified_profile_route_capabilities(
    profiles: list[VerifiedProfile],
) -> dict[str, CapabilityValue]:
    ready_profiles = [profile for profile in profiles if profile.status == "ready"]
    if not ready_profiles:
        return {}

    input_modalities = sorted(
        {
            modality
            for profile in ready_profiles
            for modality in (profile.input_modalities or [])
        }
    )
    output_modalities = sorted(
        {
            modality
            for profile in ready_profiles
            for modality in (profile.output_modalities or [])
        }
    )
    capabilities: dict[str, CapabilityValue] = {
        "verified_methods": CapabilityValue(
            value=sorted({profile.method_id for profile in ready_profiles}),
            source="probed_verified",
        ),
    }
    if input_modalities:
        capabilities["input_modalities"] = CapabilityValue(
            value=input_modalities,
            source="probed_verified",
        )
    if output_modalities:
        capabilities["output_modalities"] = CapabilityValue(
            value=output_modalities,
            source="probed_verified",
        )
    if any(_profile_supports_reasoning(profile) for profile in ready_profiles):
        capabilities["thinking_protocol"] = CapabilityValue(
            value=True,
            source="probed_verified",
        )
    return capabilities


def _profile_supports_reasoning(profile: VerifiedProfile) -> bool:
    haystack = " ".join(
        [
            profile.capability,
            profile.profile_id,
            profile.request_mapper_id,
        ]
    ).lower()
    return "thinking" in haystack or "reasoning" in haystack
