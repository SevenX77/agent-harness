"""Metadata store port for Studio skills and runs."""

from __future__ import annotations

from typing import Protocol, TypedDict

from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.models.skills import SkillSummary


class SkillIndexEntry(TypedDict):
    absolute_path: str
    l2_remote_url: str


class MetadataStore(Protocol):
    """Persist and query Studio metadata independent of storage backend."""

    async def list_skill_index(self) -> dict[str, SkillIndexEntry]:
        """Return the global skill index."""
        ...

    async def get_skill_index_entry(self, skill_id: str) -> SkillIndexEntry | None:
        """Return one skill index entry when present."""
        ...

    async def save_skill_index_entry(self, skill_id: str, entry: SkillIndexEntry) -> None:
        """Persist one skill index entry."""
        ...

    async def remove_skill_index_entry(self, skill_id: str) -> None:
        """Remove one skill index entry if present."""
        ...

    async def read_app_settings(self) -> AppSettings:
        """Return global Studio application settings."""
        ...

    async def write_app_settings(self, settings: AppSettings) -> None:
        """Persist global Studio application settings."""
        ...

    async def list_skills(self, user_id: str) -> list[SkillSummary]:
        """Return saved skill summaries for one user."""
        ...

    async def get_skill_summary(self, user_id: str, skill_id: str) -> SkillSummary | None:
        """Return one saved skill summary when present."""
        ...

    async def save_skill_summary(self, user_id: str, summary: SkillSummary) -> None:
        """Persist one skill summary for one user."""
        ...

    async def list_runs(self, user_id: str, skill_id: str) -> list[RunMetadata]:
        """Return saved run metadata for one skill."""
        ...

    async def save_run_metadata(
        self,
        user_id: str,
        skill_id: str,
        metadata: RunMetadata,
    ) -> None:
        """Persist one run metadata document for one skill."""
        ...
