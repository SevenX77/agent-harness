"""Shared LLM endpoint/route registry core."""

from __future__ import annotations

from graph_agent_gateway.registry.schema import (
    CapabilityValue,
    EffectiveRuntimeSetting,
    EndpointCandidate,
    FieldSource,
    LintResult,
    ModelProfile,
    ProbeResult,
    ProviderEndpoint,
    ProviderImportDraft,
    ProviderRoute,
    RegistrySnapshot,
    ResolvedRole,
    ResolvedRoute,
    RuntimeSettings,
    ReasoningSettings,
    RoleEntry,
    RoleRouteEntry,
    RouteCandidate,
    RuntimePolicy,
    StructuredOutputSettings,
)

__all__ = [
    "CapabilityValue",
    "EffectiveRuntimeSetting",
    "EndpointCandidate",
    "FieldSource",
    "LintResult",
    "ModelProfile",
    "ProbeResult",
    "ProviderEndpoint",
    "ProviderImportDraft",
    "ProviderRoute",
    "RegistrySnapshot",
    "ResolvedRole",
    "ResolvedRoute",
    "RuntimeSettings",
    "ReasoningSettings",
    "RoleEntry",
    "RoleRouteEntry",
    "RouteCandidate",
    "RuntimePolicy",
    "StructuredOutputSettings",
]
