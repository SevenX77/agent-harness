"""Local JSON metadata adapter for Studio run metadata."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.core.adapters.run_layout import predicts_root, runs_root
from app.core.ports.metadata import SkillIndexEntry
from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.services.run_ids import is_predict_run_id

logger = logging.getLogger(__name__)


class LocalJsonMetadataStore:
    """Metadata store that treats run_metadata.json files as records."""

    def __init__(self, global_config_dir: Path) -> None:
        self._global_config_dir = global_config_dir
        self._app_settings_lock = threading.Lock()

    async def list_skill_index(self) -> dict[str, SkillIndexEntry]:
        """Return the global skill index, tolerating missing or invalid JSON."""
        index_path = self._skill_index_path()
        if not await asyncio.to_thread(index_path.exists):
            return {}
        try:
            async with aiofiles.open(index_path, encoding="utf-8") as file:
                raw = json.loads(await file.read())
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}

        index: dict[str, SkillIndexEntry] = {}
        for skill_id, value in raw.items():
            if not isinstance(skill_id, str) or not isinstance(value, dict):
                continue
            absolute_path = value.get("absolute_path")
            if not isinstance(absolute_path, str) or not absolute_path:
                continue
            l2_remote_url = value.get("l2_remote_url")
            index[skill_id] = {
                "absolute_path": absolute_path,
                "l2_remote_url": l2_remote_url if isinstance(l2_remote_url, str) else "",
            }
        return index

    async def get_skill_index_entry(self, skill_id: str) -> SkillIndexEntry | None:
        """Return one skill index entry when present."""
        return (await self.list_skill_index()).get(skill_id)

    async def save_skill_index_entry(self, skill_id: str, entry: SkillIndexEntry) -> None:
        """Persist one skill index entry."""
        index = await self.list_skill_index()
        index[skill_id] = {
            "absolute_path": entry["absolute_path"],
            "l2_remote_url": entry.get("l2_remote_url", ""),
        }
        await self._write_skill_index(index)

    async def remove_skill_index_entry(self, skill_id: str) -> None:
        """Remove one skill index entry if present."""
        index = await self.list_skill_index()
        if skill_id not in index:
            return
        del index[skill_id]
        await self._write_skill_index(index)

    async def read_app_settings(self) -> AppSettings:
        """Return global app settings, falling back to defaults for missing or bad files."""
        return await asyncio.to_thread(self._read_app_settings_sync)

    async def write_app_settings(self, settings: AppSettings) -> None:
        """Atomically persist global app settings with user-only file permissions."""
        await asyncio.to_thread(self._write_app_settings_sync, settings)

    async def list_runs(self, user_id: str, skill_id: str) -> list[RunMetadata]:
        """Load run metadata files for one skill; an unregistered skill has none."""
        del user_id
        workspace = await self._workspace_dir(skill_id)
        if workspace is None:
            return []

        runs: list[RunMetadata] = []
        # Two roots on disk, one history on screen (decision 2026-08-09 D13).
        roots = [runs_root(workspace), predicts_root(workspace)]
        metadata_paths = await asyncio.to_thread(
            lambda: sorted(
                path for root in roots if root.exists() for path in root.glob("*/run_metadata.json")
            ),
        )
        for metadata_path in metadata_paths:
            try:
                async with aiofiles.open(metadata_path, encoding="utf-8") as file:
                    runs.append(RunMetadata.model_validate_json(str(await file.read())))
            except Exception:
                continue
        return sorted(runs, key=lambda item: item.started_at, reverse=True)

    async def save_run_metadata(
        self,
        user_id: str,
        skill_id: str,
        metadata: RunMetadata,
    ) -> None:
        """Persist one run metadata document under the indexed skill workspace."""
        del user_id
        workspace = await self._workspace_dir(skill_id)
        if workspace is None:
            raise LookupError(
                f"skill {skill_id} is not registered in Studio's skill index; "
                "cannot persist run metadata"
            )
        root = predicts_root(workspace) if is_predict_run_id(metadata.run_id) else runs_root(workspace)
        metadata_path = root / metadata.run_id / "run_metadata.json"
        await asyncio.to_thread(metadata_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(metadata_path, "w", encoding="utf-8") as file:
            await file.write(metadata.model_dump_json())

    async def _workspace_dir(self, skill_id: str) -> Path | None:
        entry = await self.get_skill_index_entry(skill_id)
        if entry is None:
            return None
        return Path(entry["absolute_path"]) / ".workspace"

    def _skill_index_path(self) -> Path:
        return self._global_config_dir / "skill_index.json"

    def _app_settings_path(self) -> Path:
        return self._global_config_dir / "app_settings.json"

    async def _write_skill_index(self, index: dict[str, SkillIndexEntry]) -> None:
        index_path = self._skill_index_path()
        await asyncio.to_thread(index_path.parent.mkdir, parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            skill_id: {
                "absolute_path": entry["absolute_path"],
                "l2_remote_url": entry.get("l2_remote_url", ""),
            }
            for skill_id, entry in sorted(index.items())
        }
        async with aiofiles.open(index_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(payload, indent=2, sort_keys=True))
            await file.write("\n")

    def _read_app_settings_sync(self) -> AppSettings:
        settings_path = self._app_settings_path()
        with self._app_settings_lock:
            if not settings_path.exists():
                return AppSettings()
            try:
                raw = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Invalid app settings JSON at %s; using defaults", settings_path)
                return AppSettings()
            try:
                return AppSettings.model_validate(raw)
            except ValidationError as exc:
                return self._salvage_app_settings(raw, settings_path, exc)

    def _salvage_app_settings(
        self,
        raw: object,
        settings_path: Path,
        error: ValidationError,
    ) -> AppSettings:
        """Recover usable settings from a forward-incompatible app_settings.json.

        A settings file written by a newer Studio (or hand-edited) can carry keys
        this build's strict ``extra="forbid"`` AppSettings model does not know —
        e.g. an older bundled backend reading a ``language`` key a later release
        added — or an out-of-range value on a key it does know. Letting that
        ValidationError propagate would 422 every endpoint that reads settings (the
        skill list reads them first), blanking the whole Home screen for an
        unrelated, recoverable reason. Drop only the offending keys/values and keep
        every other valid setting; fall back to defaults only if the survivors are
        still unusable.
        """
        if not isinstance(raw, dict):
            logger.warning("App settings at %s are invalid (%s); using defaults", settings_path, error)
            return AppSettings()
        # Unknown future keys fall away with the model-fields filter; KNOWN keys
        # whose VALUE is invalid fall away via the error locs — so one bad field
        # never discards the user's other valid settings.
        usable = {key: value for key, value in raw.items() if key in AppSettings.model_fields}
        for entry in error.errors():
            location = entry.get("loc") or ()
            if location and location[0] in usable:
                usable.pop(location[0], None)
        try:
            salvaged = AppSettings.model_validate(usable)
        except ValidationError as inner:
            logger.warning("App settings at %s are invalid (%s); using defaults", settings_path, inner)
            return AppSettings()
        logger.warning(
            "App settings at %s had unusable keys/values (%s); kept the valid known fields, dropped the rest",
            settings_path,
            error,
        )
        return salvaged

    def _write_app_settings_sync(self, settings: AppSettings) -> None:
        settings_path = self._app_settings_path()
        payload = settings.model_dump(mode="json")
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

        with self._app_settings_lock:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.parent.chmod(0o700)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{settings_path.name}.",
                suffix=".tmp",
                dir=settings_path.parent,
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                    tmp_file.write(serialized)
                    tmp_file.write("\n")
                    tmp_file.flush()
                    os.fsync(tmp_file.fileno())
                tmp_path.chmod(0o600)
                os.replace(tmp_path, settings_path)
                settings_path.chmod(0o600)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
