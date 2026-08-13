"""Media generation domain: catalog truth, credential schema, zero-cost probing.

Deliberately parallel to — and isolated from — the LLM registry: media models
are not routes and can never be selected by role→route resolution.
"""

from graph_agent_gateway.media.catalog import (
    catalog_by_id,
    runninghub_catalog,
    validate_model_settings,
)
from graph_agent_gateway.media.probing import probe_runninghub_account
from graph_agent_gateway.media.schema import (
    MediaChannel,
    MediaEndpointKind,
    MediaGenerationSnapshot,
    MediaModality,
    MediaModelSettings,
    MediaModelSpec,
    MediaParamSpec,
    MediaPricing,
    MediaProbeResult,
    MediaProbeStatus,
    MediaProviderCredential,
    MediaProviderState,
    MediaTask,
)

__all__ = [
    "MediaChannel",
    "MediaEndpointKind",
    "MediaGenerationSnapshot",
    "MediaModality",
    "MediaModelSettings",
    "MediaModelSpec",
    "MediaParamSpec",
    "MediaPricing",
    "MediaProbeResult",
    "MediaProbeStatus",
    "MediaProviderCredential",
    "MediaProviderState",
    "MediaTask",
    "catalog_by_id",
    "probe_runninghub_account",
    "runninghub_catalog",
    "validate_model_settings",
]
