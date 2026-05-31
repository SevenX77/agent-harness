"""Studio implementation of the engine SkillResolverProtocol."""

from __future__ import annotations

import json
from pathlib import Path

from graph_agent import ResourceNotFoundError
from graph_agent.core.exceptions import make_error_payload

from app.core import config


class StudioSkillResolver:
    """Resolve Studio skill ids through local index, workspace, then bundled skills."""

    def resolve_skill(self, skill_id: str) -> Path:
        indexed = _skill_index_entry(skill_id)
        if indexed:
            indexed_root = Path(indexed["absolute_path"])
            if _is_skill_root(indexed_root):
                return indexed_root
            message = f"skill {skill_id!r}: indexed path is not a skill root: {indexed_root}"
            raise ResourceNotFoundError(
                message,
                payload=make_error_payload(
                    "[F-v3-resolver-path-invalid]",
                    message,
                    skill_id=skill_id,
                    source_path=indexed_root,
                ),
            )

        workspace_root = config.default_workspace_skills_dir() / skill_id
        if _is_skill_root(workspace_root):
            return workspace_root

        bundled_root = config.SKILLS_DIR / skill_id
        if _is_skill_root(bundled_root):
            return bundled_root

        message = f"skill {skill_id!r}: skill is not registered in Studio"
        raise ResourceNotFoundError(
            message,
            payload=make_error_payload(
                "[F-v3-skill-not-registered]",
                message,
                skill_id=skill_id,
            ),
        )


def build_studio_skill_resolver() -> StudioSkillResolver:
    """Return a fresh Studio resolver for one engine call."""

    return StudioSkillResolver()


def _skill_index_entry(skill_id: str) -> dict[str, str] | None:
    index_path = config.SKILL_INDEX_PATH
    if not index_path.exists():
        return None
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    entry = raw.get(skill_id)
    if not isinstance(entry, dict) or not isinstance(entry.get("absolute_path"), str):
        return None
    return {
        "absolute_path": entry["absolute_path"],
        "l2_remote_url": (
            entry.get("l2_remote_url") if isinstance(entry.get("l2_remote_url"), str) else ""
        ),
    }


def _is_skill_root(path: Path) -> bool:
    return path.is_dir() and (path / "GRAPH.md").is_file()


__all__ = ["StudioSkillResolver", "build_studio_skill_resolver"]
