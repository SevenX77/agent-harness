"""Local JSON metadata adapter for Studio run metadata."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]

from app.core.ports.metadata import SkillIndexEntry
from app.models.runs import RunMetadata
from app.models.skills import SkillSummary


class LocalJsonMetadataStore:
    """Metadata store that treats run_metadata.json files as records."""

    def __init__(self, global_config_dir: Path, workspaces_root: Path) -> None:
        self._global_config_dir = global_config_dir
        self._workspaces_root = workspaces_root

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
