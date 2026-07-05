from __future__ import annotations

import json
import logging
from typing import Any

from app.core import config
from app.services.llm_credentials import load_credentials
from app.services.llm_paths import (
    canonical_rules_path,
    credentials_path,
    roles_path,
)
from app.services.llm_role_test_results import load_all as load_role_test_results
from app.services.llm_roles import load_roles_file
from app.services.runtime_activity import load_runtime_activity, runtime_activity_log_path
from app.services.runtime_truth_init import ensure_runtime_truth_sources


def test_ensure_runtime_truth_sources_creates_safe_empty_stores(
    studio_roots: tuple[object, object],
    caplog: Any,
) -> None:
    del studio_roots
    config.SKILL_INDEX_PATH.unlink(missing_ok=True)
    caplog.set_level(logging.INFO, logger="app.services.runtime_truth_init")

    created = ensure_runtime_truth_sources()

    assert "app_settings" in created
    assert "skill_index" in created
    assert "llm_credentials" in created
    assert "llm_roles" in created
    # Phase 9: the three legacy catalog files are no longer created or seeded — neither
    # reported in `created` nor written to disk on a clean startup.
    assert "llm_probe_catalog" not in created
    assert "community_catalog_cache" not in created
    assert "community_upload_queue" not in created
    assert config.APP_SETTINGS_PATH.exists()
    assert json.loads(config.SKILL_INDEX_PATH.read_text(encoding="utf-8")) == {}
    assert load_credentials().schema_version == 5
    assert load_roles_file(roles_path()).schema_version == 2
    assert load_role_test_results() == {}
    assert canonical_rules_path().read_text(encoding="utf-8") == "{}\n"
    assert runtime_activity_log_path().exists()
    assert not credentials_path().with_name("llm_health.sqlite").exists()
    credential_logs = load_runtime_activity(source_id="llm_credentials")
    assert credential_logs[0]["action"] == "initialize_truth_source"
    assert credential_logs[0]["message"] == "Initialized missing runtime truth source during Studio startup."
    assert "llm_credentials.json" in credential_logs[0]["changes"]["path"]
    assert any(
        "runtime_truth_init created" in record.message
        for record in caplog.records
    )


def test_ensure_runtime_truth_sources_is_idempotent(
    studio_roots: tuple[object, object],
) -> None:
    del studio_roots
    ensure_runtime_truth_sources()

    assert ensure_runtime_truth_sources() == []


def test_ensure_runtime_truth_sources_resets_invalid_roles_file(
    studio_roots: tuple[object, object],
) -> None:
    del studio_roots
    path = roles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
schema_version: 3
roles:
  analyst:
    role_kind: graph_agent
    intent:
      provider_preference: manual_order
      thinking: false
      max_output_tokens:
      temperature:
    model_groups: []
    fallback_chain: []
model_profiles: {}
model_bundles: {}
""".lstrip(),
        encoding="utf-8",
    )

    created = ensure_runtime_truth_sources()

    assert "llm_roles_reset" in created
    data = load_roles_file(path)
    assert data.roles
    assert all(role.intent.temperature == 1.4 for role in data.roles.values())
    assert "temperature:" in path.read_text(encoding="utf-8")
