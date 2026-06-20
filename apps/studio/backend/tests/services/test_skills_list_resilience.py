"""Home skill list must survive an unreadable / forward-incompatible settings file.

Regression: the running Studio reads ``app_settings.json`` at the top of
``list_skill_summaries`` (for the config-mismatch annotation). When a settings
file carried a key the build's strict ``extra="forbid"`` ``AppSettings`` model did
not know — e.g. an older bundled backend reading a ``language`` key a later
release added — ``AppSettings.model_validate`` raised a bare ``ValidationError``
that propagated to the global handler → HTTP 422, blanking EVERY skill on Home
("Could not load skills"). A recoverable settings skew must never take the whole
Home list down.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core import config
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.core.adapters.storage_local import LocalFilesystemBackend
from app.services import skills as skill_service


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
        workspaces_root=tmp_path / "workspaces",
    )


def _write_valid_graph_skill(skill_dir: Path, name: str) -> None:
    (skill_dir / "phases" / "setup").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {name}
description: Test skill
io:
  inputs:
    type: object
    properties: {{}}
  outputs:
    type: object
    properties: {{}}
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "setup" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
---
""",
        encoding="utf-8",
    )


def _write_app_settings(global_config_dir: Path, payload: dict[str, object]) -> None:
    global_config_dir.mkdir(parents=True, exist_ok=True)
    (global_config_dir / "app_settings.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


@pytest.mark.anyio
async def test_read_app_settings_salvages_known_fields_from_unknown_keys(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
) -> None:
    # A settings file with a real field plus a key this build does not know must
    # NOT raise — keep the known field, drop the unknown one.
    _write_app_settings(
        tmp_path / "global-config",
        {"user_id": "KeepMe", "some_future_studio_flag": True},
    )

    settings = await metadata_store.read_app_settings()

    assert settings.user_id == "KeepMe"
    assert not hasattr(settings, "some_future_studio_flag")


@pytest.mark.anyio
async def test_read_app_settings_keeps_valid_fields_when_one_value_is_invalid(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
) -> None:
    # An out-of-range value on a KNOWN field (language not in the supported set)
    # must drop only that field — every other valid setting survives, rather than
    # all-or-nothing defaulting.
    _write_app_settings(
        tmp_path / "global-config",
        {"user_id": "KeepMe", "language": "fr"},
    )

    settings = await metadata_store.read_app_settings()

    assert settings.user_id == "KeepMe"  # valid field preserved
    assert settings.language == "en"  # bad value dropped → field default


@pytest.mark.anyio
async def test_home_survives_forward_incompatible_app_settings(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(config, "WORKSPACES_DIR", tmp_path / "workspaces")

    # Settings file carries an unknown future key — the exact shape that 422'd the
    # live Home list when the running backend predated the key.
    _write_app_settings(
        tmp_path / "global-config",
        {"user_id": "SevenX", "some_future_studio_flag": "on"},
    )

    good_dir = tmp_path / "external" / "good-skill"
    _write_valid_graph_skill(good_dir, "good-skill")
    await metadata_store.save_skill_index_entry(
        "good-skill",
        {"absolute_path": str(good_dir), "l2_remote_url": ""},
    )

    summaries = await skill_service.list_skill_summaries(
        "default",
        LocalFilesystemBackend(tmp_path),
        metadata_store,
    )

    by_id = {summary.id: summary for summary in summaries}
    assert "good-skill" in by_id, "a settings skew must not blank the Home skill list"
    assert by_id["good-skill"].name == "good-skill"
