"""Red tests for v4->v5 credentials load upgrade — Studio LLM credentials/catalog SSOT.

T2.2 (Phase 2): a stored v4 credentials file must load and upgrade in place to v5
(route.evidence defaulted to [], last_remote_catalog_sync to None, version 5)
without dropping existing endpoints/routes. Fails until T2.3 teaches
``load_credentials`` to accept + upgrade v4 (it currently hard-rejects != 4).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.llm_credentials import load_credentials


def _write_v4_file(path: Path) -> None:
    payload = {
        "schema_version": 4,
        "provider_endpoints": {
            "openai-direct": {
                "endpoint_id": "openai-direct",
                "display_name": "OpenAI Direct",
                "protocol": "openai_compatible",
                "base_url": "https://api.example.com/v1",
            }
        },
        "provider_routes": {
            "openai-direct:gpt-5": {
                "route_id": "openai-direct:gpt-5",
                "endpoint_id": "openai-direct",
                "route_slug": "gpt-5",
                "provider_model_id": "gpt-5",
                "canonical_id": "gpt-5",
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_v4_file_loads_and_upgrades_to_v5(tmp_path: Path) -> None:
    path = tmp_path / "llm_credentials.json"
    _write_v4_file(path)

    loaded = load_credentials(path)

    assert loaded.schema_version == 5
    # existing endpoints/routes survive the upgrade
    assert "openai-direct" in loaded.provider_endpoints
    route = loaded.provider_routes["openai-direct:gpt-5"]
    # new fields are defaulted
    assert route.evidence == []
    assert loaded.last_remote_catalog_sync is None
