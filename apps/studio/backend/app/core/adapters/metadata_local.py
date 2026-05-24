"""Local JSON metadata adapter for Studio run metadata."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]
from graph_agent.core.manifest import GraphManifest
from graph_agent.core.parser import parse_markdown_parts
from graph_agent.core.skill_resolver_protocol import validate_skill_id

from app.core.paths import default_skills_root
from app.core.ports.metadata import SkillIndexEntry
from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.models.skills import SkillSummary

logger = logging.getLogger(__name__)


def _rmtree_if_exists(path: Path) -> None:
    """Remove a directory tree if it exists; no-op when missing."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=False)


class LocalJsonMetadataStore:
    """Metadata store that treats run_metadata.json files as records."""

    def __init__(self, global_config_dir: Path, workspaces_root: Path) -> None:
        self._global_config_dir = global_config_dir
        self._workspaces_root = workspaces_root
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

    async def import_skill_directory(
        self,
        user_id: str,
        target_skill_id: str,
        directory_path: str,
    ) -> SkillSummary:
        """Validate and register an existing V0.3.0 graph skill directory."""
        del user_id
        summary = await asyncio.to_thread(
            self._validate_import_skill_directory_sync,
            target_skill_id,
            directory_path,
        )
        registry_path = self._registry_summary_path(target_skill_id)
        await asyncio.to_thread(registry_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(registry_path, "w", encoding="utf-8") as file:
            await file.write(summary.model_dump_json())
        await self.save_skill_index_entry(
            target_skill_id,
            {"absolute_path": summary.directory_path or "", "l2_remote_url": ""},
        )
        return summary

    def resolve_registered_skill_path(self, skill_id: str) -> Path:
        """Resolve a Studio registered skill id to its graph skill root."""
        validate_skill_id(skill_id)
        index_path = self._skill_index_path()
        if index_path.exists():
            try:
                raw = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
            if isinstance(raw, dict):
                entry = raw.get(skill_id)
                if isinstance(entry, dict) and isinstance(entry.get("absolute_path"), str):
                    path = Path(entry["absolute_path"]).resolve()
                    if path.is_dir() and (path / "GRAPH.md").is_file():
                        return path

        registry_path = self._registry_summary_path(skill_id)
        if registry_path.exists():
            summary = SkillSummary.model_validate_json(
                registry_path.read_text(encoding="utf-8")
            )
            if summary.directory_path:
                path = Path(summary.directory_path).resolve()
                if path.is_dir() and (path / "GRAPH.md").is_file():
                    return path
        raise FileNotFoundError(skill_id)

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

    async def remove_skill_summary(self, user_id: str, skill_id: str) -> None:
        """Remove one user's skill summary and any cached runs under it."""
        skill_root = self._skills_root(user_id) / skill_id
        await asyncio.to_thread(_rmtree_if_exists, skill_root)

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

    def _registry_summary_path(self, skill_id: str) -> Path:
        return default_skills_root(self._global_config_dir) / skill_id / "skill_summary.json"

    async def _runs_root(self, user_id: str, skill_id: str) -> Path:
        entry = await self.get_skill_index_entry(skill_id)
        if entry:
            return Path(entry["absolute_path"]) / ".workspace" / "runs"
        return self._skills_root(user_id) / skill_id / "runs"

    def _skill_index_path(self) -> Path:
        return self._global_config_dir / "skill_index.json"

    def _validate_import_skill_directory_sync(
        self,
        target_skill_id: str,
        directory_path: str,
    ) -> SkillSummary:
        validate_skill_id(target_skill_id)
        skill_dir = Path(directory_path).expanduser().resolve()
        if not skill_dir.is_dir():
            raise ValueError(f"directory_path is not a directory: {skill_dir}")
        graph_path = skill_dir / "GRAPH.md"
        if not graph_path.is_file():
            raise ValueError(f"directory_path has no GRAPH.md: {skill_dir}")
        frontmatter, _body, _line_meta = parse_markdown_parts(graph_path)
        manifest = GraphManifest.model_validate(frontmatter)
        if manifest.name != target_skill_id:
            raise ValueError(
                "GRAPH.md name must match target_skill_id: "
                f"{manifest.name!r} != {target_skill_id!r}"
            )
        return SkillSummary(
            id=target_skill_id,
            name=manifest.name,
            description=manifest.description,
            phase_count=len(manifest.phases),
            has_golden=(skill_dir / "golden").exists(),
            directory_path=str(skill_dir),
        )

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
            return AppSettings.model_validate(raw)

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
