"""Shared LLM endpoint/route registry core."""

from __future__ import annotations

from graph_agent_gateway.registry.schema import (
    CapabilityValue,
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
    RoleEntry,
    RoleRouteEntry,
    RouteCandidate,
    RuntimePolicy,
)

__all__ = [
    "CapabilityValue",
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
    "RoleEntry",
    "RoleRouteEntry",
    "RouteCandidate",
    "RuntimePolicy",
]
