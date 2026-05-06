"""Metadata store port for Studio skills and runs."""

from __future__ import annotations

from typing import Protocol

from app.models.runs import RunMetadata
from app.models.skills import SkillSummary


class MetadataStore(Protocol):
    """Persist and query Studio metadata independent of storage backend."""

    async def list_skills(self, user_id: str) -> list[SkillSummary]:
        """Return saved skill summaries for one user."""
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
