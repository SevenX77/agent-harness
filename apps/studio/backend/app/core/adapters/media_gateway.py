"""Studio boundary for the Gateway media generation domain.

The single import point for ``graph_agent_gateway.media``: Studio services and
routers consume the media catalog/schema/probe through this adapter so the SDK
surface stays behind one reviewed boundary (same pattern as ``gateway.py``).
"""

from __future__ import annotations

from graph_agent_gateway.media import (
    MediaGenerationSnapshot,
    MediaModelSettings,
    MediaModelSpec,
    MediaProbeResult,
    MediaProviderCredential,
    catalog_by_id,
    probe_runninghub_account,
    runninghub_catalog,
    validate_model_settings,
)

__all__ = [
    "MediaGenerationSnapshot",
    "MediaModelSettings",
    "MediaModelSpec",
    "MediaProbeResult",
    "MediaProviderCredential",
    "catalog_by_id",
    "probe_runninghub_account",
    "runninghub_catalog",
    "validate_model_settings",
]
