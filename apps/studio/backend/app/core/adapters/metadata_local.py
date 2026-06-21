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

from app.core.ports.metadata import SkillIndexEntry
from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.models.skills import SkillSummary

logger = logging.getLogger(__name__)


class LocalJsonMetadataStore:
    """Metadata store that treats run_metadata.json files as records."""

    def __init__(self, global_config_dir: Path, workspaces_root: Path) -> None:
        self._global_config_dir = global_config_dir
        self._workspaces_root = workspaces_root
        self._app_settings_lock = threading.Lock()
        self._unregistered_skills_lock = threading.Lock()

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

    async def list_unregistered_skill_ids(self, user_id: str) -> set[str]:
        """Return skill ids hidden from Studio for one user."""
        return await asyncio.to_thread(self._read_unregistered_skill_ids_sync, user_id)

    async def unregister_skill(self, user_id: str, skill_id: str) -> None:
        """Hide one skill id from Studio without deleting its source files."""
        await asyncio.to_thread(self._update_unregistered_skill_id_sync, user_id, skill_id, True)

    async def register_skill(self, user_id: str, skill_id: str) -> None:
        """Make one previously hidden skill id visible in Studio again."""
        await asyncio.to_thread(self._update_unregistered_skill_id_sync, user_id, skill_id, False)

    async def read_app_settings(self) -> AppSettings:
        """Return global app settings, falling back to defaults for missing or bad files."""
        return await asyncio.to_thread(self._read_app_settings_sync)

    async def write_app_settings(self, settings: AppSettings) -> None:
        """Atomically persist global app settings with user-only file permissions."""
        await asyncio.to_thread(self._write_app_settings_sync, settings)

    async def list_skills(self, user_id: str) -> list[SkillSummary]:
        """Return persisted skill summaries when present."""
        skills_root = self._skills_root(user_id)
        if not await asyncio.to_thread(skills_root.exists):
            return []

        summaries: list[SkillSummary] = []
        for summary_path in await asyncio.to_thread(
            lambda: sorted(skills_root.glob("*/skill_summary.json")),
        ):
            try:
                async with aiofiles.open(summary_path, encoding="utf-8") as file:
                    summaries.append(SkillSummary.model_validate_json(str(await file.read())))
            except Exception:
                continue
        return summaries

    async def get_skill_summary(self, user_id: str, skill_id: str) -> SkillSummary | None:
        """Return one persisted skill summary when present."""
        summary_path = self._skills_root(user_id) / skill_id / "skill_summary.json"
        if not await asyncio.to_thread(summary_path.exists):
            return None
        try:
            async with aiofiles.open(summary_path, encoding="utf-8") as file:
                return SkillSummary.model_validate_json(str(await file.read()))
        except Exception:
            return None

    async def save_skill_summary(self, user_id: str, summary: SkillSummary) -> None:
        """Persist one skill summary as JSON."""
        summary_path = self._skills_root(user_id) / summary.id / "skill_summary.json"
        await asyncio.to_thread(summary_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(summary_path, "w", encoding="utf-8") as file:
            await file.write(summary.model_dump_json())
        await self.register_skill(user_id, summary.id)

    async def remove_skill_summary(self, user_id: str, skill_id: str) -> None:
        """Remove one user's saved skill summary without touching skill source files."""
        summary_path = self._skills_root(user_id) / skill_id / "skill_summary.json"
        if await asyncio.to_thread(summary_path.exists):
            await asyncio.to_thread(summary_path.unlink)

    async def list_runs(self, user_id: str, skill_id: str) -> list[RunMetadata]:
        """Load run metadata files for one skill."""
        runs_root = await self._runs_root(user_id, skill_id)
        if not await asyncio.to_thread(runs_root.exists):
            return []

        runs: list[RunMetadata] = []
        metadata_paths = await asyncio.to_thread(
            lambda: sorted(runs_root.glob("*/run_metadata.json")),
        )
        for metadata_path in metadata_paths:
            if metadata_path.parent.name == "latest":
                continue
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
        """Persist one run metadata document."""
        metadata_path = (
            (await self._runs_root(user_id, skill_id)) / metadata.run_id / "run_metadata.json"
        )
        await asyncio.to_thread(metadata_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(metadata_path, "w", encoding="utf-8") as file:
            await file.write(metadata.model_dump_json())

    def _skills_root(self, user_id: str) -> Path:
        return self._workspaces_root / user_id / "skills"

    async def _runs_root(self, user_id: str, skill_id: str) -> Path:
        entry = await self.get_skill_index_entry(skill_id)
        if entry:
            return Path(entry["absolute_path"]) / ".workspace" / "runs"
        return self._skills_root(user_id) / skill_id / "runs"

    def _skill_index_path(self) -> Path:
        return self._global_config_dir / "skill_index.json"

    def _app_settings_path(self) -> Path:
        return self._global_config_dir / "app_settings.json"

    def _unregistered_skills_path(self) -> Path:
        return self._global_config_dir / "unregistered_skills.json"

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

    def _read_unregistered_skill_ids_sync(self, user_id: str) -> set[str]:
        with self._unregistered_skills_lock:
            payload = self._read_unregistered_skills_payload_unlocked()
            return set(payload.get(user_id, set()))

    def _update_unregistered_skill_id_sync(
        self,
        user_id: str,
        skill_id: str,
        hidden: bool,
    ) -> None:
        with self._unregistered_skills_lock:
            payload = self._read_unregistered_skills_payload_unlocked()
            ids = set(payload.get(user_id, set()))
            if hidden:
                ids.add(skill_id)
            else:
                ids.discard(skill_id)
            if ids:
                payload[user_id] = ids
            else:
                payload.pop(user_id, None)
            self._write_unregistered_skills_payload_unlocked(payload)

    def _read_unregistered_skills_payload_unlocked(self) -> dict[str, set[str]]:
        path = self._unregistered_skills_path()
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        payload: dict[str, set[str]] = {}
        for user_id, value in raw.items():
            if not isinstance(user_id, str) or not isinstance(value, list):
                continue
            payload[user_id] = {item for item in value if isinstance(item, str) and item}
        return payload

    def _write_unregistered_skills_payload_unlocked(self, payload: dict[str, set[str]]) -> None:
        path = self._unregistered_skills_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            user_id: sorted(ids)
            for user_id, ids in sorted(payload.items())
            if ids
        }
        path.write_text(
            json.dumps(serializable, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
