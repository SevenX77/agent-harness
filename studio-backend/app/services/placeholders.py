"""Small validated placeholder objects for Phase 0 API scaffolding."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.core.config import SKILLS_DIR, WORKSPACES_DIR
from app.models.runs import RunDetail, RunMetadata, TokensMetrics
from app.models.skills import SkillDetail, SkillSummary
from app.models.terminal import TerminalSession
from graph_agent.core.manifest import AgentProfile, AgentSkillDef


def now_utc() -> datetime:
    """Return an aware timestamp for API placeholder data."""
    return datetime.now(UTC)


def placeholder_manifest(skill_id: str) -> AgentSkillDef:
    """Return a minimal valid graph_agent SkillManifest concrete variant."""
    return AgentSkillDef(
        schema_version="2.0",
        type="agent",
        name=skill_id,
        description="Phase 0 Studio placeholder skill",
        agent_profile=AgentProfile(
            role="Studio scaffold",
            goal="Keep API schemas available until engine integration lands.",
            steps=["Return typed placeholder data."],
        ),
    )


def placeholder_skill_summary(
    skill_id: str = "phase0-placeholder",
    description: str = "Phase 0 Studio placeholder skill",
) -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name=skill_id,
        description=description,
        phase_count=0,
        has_golden=False,
        last_run_at=None,
    )


def placeholder_run_metadata(
    skill_id: str,
    run_id: str | None = None,
    status: Literal["running", "success", "failed"] = "running",
) -> RunMetadata:
    normalized_run_id = run_id or f"{skill_id}-phase0-run"
    return RunMetadata(
        run_id=normalized_run_id,
        status=status,
        started_at=now_utc(),
        metrics=TokensMetrics(input_tokens=0, output_tokens=0, total_tokens=0),
    )


def placeholder_skill_detail(skill_id: str) -> SkillDetail:
    skill_dir = WORKSPACES_DIR / "default" / "skills" / skill_id
    return SkillDetail(
        manifest=placeholder_manifest(skill_id),
        file_paths={
            "skill_md": str(skill_dir / "SKILL.md"),
            "public_template_dir": str(SKILLS_DIR / skill_id),
            "workspace_skill_dir": str(skill_dir),
        },
        has_golden=False,
        latest_run_metadata=None,
    )


def placeholder_run_detail(skill_id: str, run_id: str) -> RunDetail:
    return RunDetail(
        metadata=placeholder_run_metadata(skill_id=skill_id, run_id=run_id, status="success"),
        events=[],
        final_context={},
        artifacts=[],
    )


def placeholder_terminal_session(skill_id: str) -> TerminalSession:
    skill_dir = WORKSPACES_DIR / "default" / "skills" / skill_id
    term_id = f"{skill_id}-phase0-terminal"
    return TerminalSession(
        term_id=term_id,
        ws_url=f"/ws/terminal/{term_id}",
        cwd=str(skill_dir),
        ttl_seconds=3600,
    )
