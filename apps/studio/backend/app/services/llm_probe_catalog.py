"""Studio service facade for the Probe Knowledge Catalog.

The storage implementation still lives in ``llm_import_drafts`` for migration
compatibility; this module is the canonical import path for new code.
"""

from __future__ import annotations

from app.services.llm_import_drafts import (
    EVIDENCE_LIBRARY_DRAFT_ID,
    RemoteCatalogSourceMetadata,
    RemoteCatalogSyncError,
    RemoteCatalogSyncResult,
    append_evidence_record,
    load_evidence_library,
    load_remote_catalog_source_metadata,
    new_evidence_id,
    remember_remote_catalog_source,
)
from app.services.llm_import_drafts import (
    sync_remote_evidence_library as _sync_remote_evidence_library,
)
from app.services.llm_import_drafts import (
    sync_remote_evidence_library_with_metadata as _sync_remote_evidence_library_with_metadata,
)

sync_remote_probe_catalog = _sync_remote_evidence_library
sync_remote_probe_catalog_with_metadata = _sync_remote_evidence_library_with_metadata

__all__ = [
    "EVIDENCE_LIBRARY_DRAFT_ID",
    "RemoteCatalogSourceMetadata",
    "RemoteCatalogSyncError",
    "RemoteCatalogSyncResult",
    "append_evidence_record",
    "load_evidence_library",
    "load_remote_catalog_source_metadata",
    "new_evidence_id",
    "remember_remote_catalog_source",
    "sync_remote_probe_catalog",
    "sync_remote_probe_catalog_with_metadata",
]
