"""Probe Knowledge Catalog storage and derivation public API.

The implementation currently reuses the legacy import-draft store types for
backward compatibility. New callers should import from this module.
"""

from __future__ import annotations

from graph_agent_gateway.import_draft_store import (
    EVIDENCE_LIBRARY_DRAFT_ID,
    ImportDraftStore,
    MaterializedImportDraftCandidates,
    PromotableRouteUpdate,
    known_model_ids_for_endpoint,
    known_verified_capabilities,
    materialize_import_draft_candidates,
    merge_evidence_library,
    new_evidence_library,
    probe_priority,
    promotable_route_update,
)

ProbeCatalogStore = ImportDraftStore
MaterializedProbeCatalogCandidates = MaterializedImportDraftCandidates
materialize_probe_catalog_candidates = materialize_import_draft_candidates

__all__ = [
    "EVIDENCE_LIBRARY_DRAFT_ID",
    "MaterializedProbeCatalogCandidates",
    "ProbeCatalogStore",
    "PromotableRouteUpdate",
    "known_model_ids_for_endpoint",
    "known_verified_capabilities",
    "materialize_probe_catalog_candidates",
    "merge_evidence_library",
    "new_evidence_library",
    "probe_priority",
    "promotable_route_update",
]
