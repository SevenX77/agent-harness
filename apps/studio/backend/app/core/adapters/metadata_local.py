"""Local JSON metadata adapter for Studio run metadata."""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiofiles  # type: ignore[import-untyped]

from app.models.runs import RunMetadata
from app.models.skills import SkillSummary


class LocalJsonMetadataStore:
    """Metadata store that treats run_metadata.json files as records."""

    def __init__(self, workspaces_root: Path) -> None:
        self._workspaces_root = workspaces_root

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
        runs_root = self._skills_root(user_id) / skill_id / "runs"
        if not await asyncio.to_thread(runs_root.exists):
            return []

        runs: list[RunMetadata] = []
        metadata_paths = await asyncio.to_thread(
            lambda: sorted(runs_root.glob("*/run_metadata.json")),
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
        """Persist one run metadata document."""
        metadata_path = (
            self._skills_root(user_id) / skill_id / "runs" / metadata.run_id / "run_metadata.json"
        )
        await asyncio.to_thread(metadata_path.parent.mkdir, parents=True, exist_ok=True)
        async with aiofiles.open(metadata_path, "w", encoding="utf-8") as file:
            await file.write(metadata.model_dump_json())

    def _skills_root(self, user_id: str) -> Path:
        return self._workspaces_root / user_id / "skills"
