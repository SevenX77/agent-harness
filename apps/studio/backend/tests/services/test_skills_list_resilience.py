"""read_app_settings must tolerate a forward-incompatible / invalid settings file.

A settings file can carry a key the running build's strict ``extra="forbid"``
``AppSettings`` model does not know (e.g. an older bundled backend reading a
``language`` key a later release added), or an out-of-range value on a known key.
Reading it must NOT raise a bare ``ValidationError`` — that previously propagated
to the global handler → HTTP 422 on every endpoint that reads settings. The read
path salvages the usable fields instead (``_salvage_app_settings``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.adapters.metadata_local import LocalJsonMetadataStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def metadata_store(tmp_path: Path) -> LocalJsonMetadataStore:
    return LocalJsonMetadataStore(
        global_config_dir=tmp_path / "global-config",
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
async def test_salvaging_the_retired_catalog_toggle_lands_on_unset_never_shared(
    tmp_path: Path,
    metadata_store: LocalJsonMetadataStore,
) -> None:
    """A pre-existing file with ONLY the retired ``remote_model_catalog_enabled``
    bool (no ``community_sharing_choice`` at all) must salvage to ``"unset"`` —
    never ``"shared"`` and never ``"declined"``.

    This is the exact shape a real machine's on-disk settings had before this
    field was introduced. The old bool being ``True`` recorded nothing about
    user intent (it was ship-default, on before anyone was ever asked), so
    translating it into any answered state would silently manufacture consent
    the user never gave — exactly the defect the first-run consent dialog
    exists to fix. The generic salvage path (`_salvage_app_settings`) already
    gets this right structurally: it filters `raw` down to keys the CURRENT
    model recognizes, `remote_model_catalog_enabled` is not one of them, so
    `community_sharing_choice` is simply absent from the survivors and falls
    through to its own field default — this test pins that behavior so a
    future change cannot regress it into treating "never asked" as consent.
    """
    _write_app_settings(
        tmp_path / "global-config",
        {"user_id": "KeepMe", "remote_model_catalog_enabled": True},
    )

    settings = await metadata_store.read_app_settings()

    assert settings.user_id == "KeepMe"
    assert settings.community_sharing_choice == "unset"
    assert not hasattr(settings, "remote_model_catalog_enabled")
