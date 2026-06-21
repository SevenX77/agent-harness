from __future__ import annotations

import json
from pathlib import Path

from app.models.llm_config import ProviderImportDraft


def test_repository_root_remote_catalog_seed_is_public_safe() -> None:
    root = Path(__file__).resolve().parents[5]
    catalog_path = root / "llm_import_drafts.json"

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    draft = ProviderImportDraft.model_validate(payload["drafts"]["studio-evidence-library"])
    serialized = json.dumps(payload)
    evidence_ids = [record.evidence_id for record in draft.evidence_records]

    assert draft.draft_id == "studio-evidence-library"
    assert "api_key" not in serialized
    assert "authorization" not in serialized.lower()
    assert "custom-" not in serialized
    assert "openrouter-prod" not in serialized
    assert "qiniu-anthropic" not in serialized
    assert "wavespeed-prod" not in serialized
    assert len(evidence_ids) == len(set(evidence_ids))
