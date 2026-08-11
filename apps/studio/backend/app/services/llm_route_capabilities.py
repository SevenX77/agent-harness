"""Helpers for deriving route capabilities from verified invocation profiles."""

from __future__ import annotations

from app.core.adapters.gateway import VerifiedProfile
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

    input_modalities = sorted({modality for profile in ready_profiles for modality in (profile.input_modalities or [])})
    output_modalities = sorted(
        {modality for profile in ready_profiles for modality in (profile.output_modalities or [])}
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


_REASONING_CAPABILITIES = frozenset({"thinking", "reasoning"})
"""The capability names a probe candidate declares when it asks the model to think.

The candidate tables (`app/data/probe_candidates.json`,
`probe_candidates_dynamic.json`) name each candidate's capability outright —
`text_chat`, `thinking`, or `reasoning`. Reading that field is what makes
`thinking_protocol` measured: a candidate declared `thinking` that came back
`ready` means a request shaped for thinking was accepted.
"""


def _profile_supports_reasoning(profile: VerifiedProfile) -> bool:
    """Whether this profile's probe asked the model to think, and got a yes.

    Decided by the declared capability, not by searching the profile's
    identifiers for the substring "thinking" — a name is a label, and the
    conclusion here is stamped `probed_verified`. It also gates whether Studio
    spends one request per effort level, so guessing it wrong costs money in one
    direction and leaves the levels unmeasured in the other.
    """
    return profile.capability in _REASONING_CAPABILITIES
