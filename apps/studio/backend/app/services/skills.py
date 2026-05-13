"""Skill filesystem and graph_agent compile integration."""

from __future__ import annotations

import contextlib
import json
import re
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder
from graph_agent import compile_skill
from graph_agent.core.compiler import CompileIssue
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentSkillDef, GraphSkillDef, PersonaSkillDef, SkillManifest
from graph_agent.core.parser import parse_skill_file
from pydantic import TypeAdapter

from app.core import config
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import LintError
from app.models.lint import LintResult
from app.models.runs import RunMetadata
from app.models.skills import SkillDetail, SkillSummary

_LOCATION_RE = re.compile(r"SKILL\.md:(?P<line>\d+)(?::(?P<loc>.*))?$")
_NAME_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>name:\s*)(?P<quote>['\"]?)(?P<value>[^'\"\n]+)(?P=quote)\s*$"
)
_ID_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>id:\s*)(?P<quote>['\"]?)(?P<value>[^'\"\n]+)(?P=quote)\s*$"
)


def ensure_workspace_layout() -> None:
    """Create the writable Studio workspace skeleton."""
    config.default_workspace_skills_dir().mkdir(parents=True, exist_ok=True)


async def list_skill_summaries(
    user_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> list[SkillSummary]:
    """Return public, workspace, and imported directory skills."""
    summaries: dict[str, SkillSummary] = {}
    public_ids = await _list_skill_ids(config.SKILLS_DIR, storage)
    workspace_root = _workspace_skills_dir_for(user_id)
    workspace_ids = await _list_skill_ids(workspace_root, storage)
    metadata_summaries = await metadata.list_skills(user_id)
    for skill_id in public_ids:
        skill_dir = config.SKILLS_DIR / skill_id
        summaries[skill_id] = await _summary_for_skill_dir_async(
            user_id,
            skill_dir,
            storage,
            metadata,
        )
    for skill_id in workspace_ids:
        skill_dir = workspace_root / skill_id
        summaries[skill_id] = await _summary_for_skill_dir_async(
            user_id,
            skill_dir,
            storage,
            metadata,
        )
    for saved_summary in metadata_summaries:
        if not saved_summary.directory_path:
            continue
        skill_dir = Path(saved_summary.directory_path)
        if not await storage.exists(str(skill_dir / "SKILL.md")):
            continue
        summaries[saved_summary.id] = (
            await _summary_for_skill_dir_async(
                user_id,
                skill_dir,
                storage,
                metadata,
                skill_id=saved_summary.id,
            )
        ).model_copy(update={"directory_path": saved_summary.directory_path})
    return sorted(summaries.values(), key=lambda summary: summary.id)


async def get_skill_detail(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
    *,
    lint_result: LintResult | None = None,
) -> SkillDetail:
    """Compile one skill into a Studio SkillDetail response."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    skill_path = skill_dir / "SKILL.md"
    lint = lint_result or lint_skill_path(skill_path)
    if lint.status == "failed":
        _raise_manifest_validation_failed(lint)
    manifest = _load_manifest(skill_path)
    return await _detail_from_manifest_async(
        user_id,
        skill_id,
        skill_dir,
        manifest,
        lint,
        storage,
        metadata,
    )


def lint_skill(skill_id: str) -> LintResult:
    """Lint a resolved skill by id."""
    return lint_skill_path(resolve_skill_dir(skill_id) / "SKILL.md")


def lint_skill_path(skill_path: Path) -> LintResult:
    """Convert graph_agent CompileResult into Studio LintResult."""
    result = compile_skill(skill_path)
    errors = [_lint_error_from_issue(issue) for issue in result.issues]
    return LintResult(
        status="passed" if result.passed else "failed",
        errors=errors,
        phases_summary=_phase_summary_from_frontmatter(skill_path) if result.passed else None,
    )


async def update_skill_content(
    user_id: str,
    skill_id: str,
    content: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    """Validate then atomically write SKILL.md into the skill's writable directory."""
    if not content.strip():
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message="Skill content must not be empty",
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    target_dir = await ensure_workspace_skill_dir_async(user_id, skill_id, storage, metadata)
    target_path = target_dir / "SKILL.md"
    candidate_path = target_dir / f".SKILL.{uuid.uuid4().hex}.tmp"
    await storage.write_text(str(candidate_path), content)
    try:
        lint = lint_skill_path(candidate_path)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
        _load_manifest(candidate_path)
        await storage.move(str(candidate_path), str(target_path))
    finally:
        await storage.delete(str(candidate_path))

    return await get_skill_detail(user_id, skill_id, storage, metadata, lint_result=lint)


async def create_new_skill(
    user_id: str,
    skill_id: str,
    content: str,
    storage: StorageBackend,
    metadata: MetadataStore,
    directory_path: str | None = None,
) -> SkillSummary:
    """Create a new skill from fully rendered SKILL.md content."""
    if not content.strip():
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message="Skill content must not be empty",
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    saved_summary = await metadata.get_skill_summary(user_id, skill_id)
    index_entry = await metadata.get_skill_index_entry(skill_id)
    if saved_summary is not None or index_entry is not None:
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    skill_dir = (
        await _validated_directory_path(user_id, skill_id, directory_path, metadata)
        if directory_path
        else config.DEFAULT_SKILLS_ROOT / skill_id
    )
    public_path = config.SKILLS_DIR / skill_id / "SKILL.md"
    skill_path = skill_dir / "SKILL.md"
    if await storage.exists(str(skill_path)) or await storage.exists(str(public_path)):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    await storage.write_text(str(skill_path), content)
    summary = await _summary_for_skill_dir_async(
        user_id,
        skill_dir,
        storage,
        metadata,
        skill_id=skill_id,
    )
    summary = summary.model_copy(update={"directory_path": str(skill_dir)})
    await metadata.save_skill_index_entry(
        skill_id,
        {"absolute_path": str(skill_dir), "l2_remote_url": ""},
    )
    await metadata.save_skill_summary(user_id, summary)
    return summary


async def fork_skill(
    user_id: str,
    skill_id: str,
    new_skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillSummary:
    """Clone an existing skill into the user's workspace under a new id."""
    workspace_root = _workspace_skills_dir_for(user_id)
    target_dir = workspace_root / new_skill_id
    target_path = target_dir / "SKILL.md"
    public_collision = config.SKILLS_DIR / new_skill_id / "SKILL.md"
    if await storage.exists(str(target_path)) or await storage.exists(str(public_collision)):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {new_skill_id}",
            {"skill_id": new_skill_id},
        )

    source_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    await storage.copy_tree(str(source_dir), str(target_dir))
    try:
        content = await storage.read_text(str(target_path))
        await storage.write_text(
            str(target_path),
            _rewrite_forked_skill_content(content, old_id=skill_id, new_id=new_skill_id),
        )
        lint = lint_skill_path(target_path)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
        summary = await _summary_for_skill_dir_async(user_id, target_dir, storage, metadata)
        await metadata.save_skill_summary(user_id, summary)
        return summary
    except Exception:
        await storage.delete(str(target_dir))
        raise


async def ensure_workspace_skill_dir_async(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> Path:
    """Return the writable skill body directory without creating workspace forks."""
    indexed = await metadata.get_skill_index_entry(skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if await storage.exists(str(skill_dir / "SKILL.md")):
            return skill_dir

    saved_summary = await metadata.get_skill_summary(user_id, skill_id)
    if saved_summary and saved_summary.directory_path:
        skill_dir = Path(saved_summary.directory_path)
        if await storage.exists(str(skill_dir / "SKILL.md")):
            return skill_dir

    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await storage.exists(str(workspace_dir / "SKILL.md")):
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if await storage.exists(str(public_dir / "SKILL.md")):
        response = error_response(
            error_code="SKILL_READ_ONLY",
            http_status=403,
            message=f"Skill is read-only: {skill_id}",
            details={"skill_id": skill_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


async def resolve_skill_dir_async(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> Path:
    """Resolve a skill id through the global index, then legacy and builtin paths."""
    indexed = await metadata.get_skill_index_entry(skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if await storage.exists(str(skill_dir / "SKILL.md")):
            return skill_dir

    saved_summary = await metadata.get_skill_summary(user_id, skill_id)
    if saved_summary and saved_summary.directory_path:
        return Path(saved_summary.directory_path)

    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await storage.exists(str(workspace_dir / "SKILL.md")):
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if await storage.exists(str(public_dir / "SKILL.md")):
        return public_dir
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


async def latest_run_metadata_async(
    user_id: str,
    skill_id: str,
    metadata: MetadataStore,
) -> RunMetadata | None:
    """Return the newest persisted run metadata for one skill via MetadataStore."""
    candidates = await metadata.list_runs(user_id, skill_id)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.started_at)


def ensure_workspace_skill_dir(skill_id: str) -> Path:
    """Return a writable skill dir without creating workspace forks."""
    indexed = _sync_skill_index_entry(skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if (skill_dir / "SKILL.md").exists():
            return skill_dir

    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if workspace_dir.exists():
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if (public_dir / "SKILL.md").exists():
        response = error_response(
            error_code="SKILL_READ_ONLY",
            http_status=403,
            message=f"Skill is read-only: {skill_id}",
            details={"skill_id": skill_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


def resolve_skill_dir(skill_id: str) -> Path:
    """Resolve a skill id, preferring the global index."""
    indexed = _sync_skill_index_entry(skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if (skill_dir / "SKILL.md").exists():
            return skill_dir

    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if (workspace_dir / "SKILL.md").exists():
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if (public_dir / "SKILL.md").exists():
        return public_dir
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


def run_dir_for(skill_id: str, run_id: str) -> Path:
    """Return the Studio V3 run directory for a skill run."""
    return runs_dir_for(resolve_skill_dir(skill_id)) / run_id


def workspace_dir_for(skill_dir: Path) -> Path:
    return skill_dir / ".workspace"


def runs_dir_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "runs"


def golden_dir_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "golden"


def predict_dir_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "predict"


def local_settings_path_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "local_settings.json"


def test_inputs_dir_for_skill(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "test_inputs"


def skill_id_from_changed_path(path: Path) -> str | None:
    """Map a changed file path under watched roots back to a skill id."""
    resolved = path.resolve()
    roots = (config.default_workspace_skills_dir(), config.SKILLS_DIR)
    for root in roots:
        try:
            relative = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if relative.parts:
            return relative.parts[0]
    return None


def latest_run_metadata(skill_id: str) -> RunMetadata | None:
    """Return the newest persisted run metadata for one skill."""
    runs_dir = runs_dir_for(resolve_skill_dir(skill_id))
    if not runs_dir.exists():
        return None
    candidates: list[RunMetadata] = []
    for metadata_path in runs_dir.glob("*/run_metadata.json"):
        if metadata_path.parent.name == "latest":
            continue
        try:
            candidates.append(
                RunMetadata.model_validate_json(metadata_path.read_bytes().decode("utf-8")),
            )
        except Exception:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.started_at)


def _iter_skill_dirs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if (path / "SKILL.md").is_file())


def _summary_for_skill_dir(skill_dir: Path) -> SkillSummary:
    skill_id = skill_dir.name
    lint = lint_skill_path(skill_dir / "SKILL.md")
    if lint.status == "passed":
        frontmatter = _frontmatter(skill_dir / "SKILL.md")
        name = str(frontmatter.get("name") or skill_id)
        description = str(frontmatter.get("description") or "")
        phase_count = _phase_count_from_frontmatter(frontmatter)
    else:
        name = skill_id
        description = lint.errors[0].message if lint.errors else "Invalid skill manifest"
        phase_count = 0
    latest = latest_run_metadata(skill_id)
    return SkillSummary(
        id=skill_id,
        name=name,
        description=description,
        phase_count=phase_count,
        has_golden=_has_golden(skill_dir),
        last_run_at=latest.started_at if latest else None,
    )


async def _summary_for_skill_dir_async(
    user_id: str,
    skill_dir: Path,
    storage: StorageBackend,
    metadata: MetadataStore,
    *,
    skill_id: str | None = None,
) -> SkillSummary:
    resolved_skill_id = skill_id or skill_dir.name
    lint = lint_skill_path(skill_dir / "SKILL.md")
    if lint.status == "passed":
        frontmatter = _frontmatter(skill_dir / "SKILL.md")
        name = str(frontmatter.get("name") or resolved_skill_id)
        description = str(frontmatter.get("description") or "")
        phase_count = _phase_count_from_frontmatter(frontmatter)
    else:
        name = resolved_skill_id
        description = lint.errors[0].message if lint.errors else "Invalid skill manifest"
        phase_count = 0
    latest = await latest_run_metadata_async(user_id, resolved_skill_id, metadata)
    return SkillSummary(
        id=resolved_skill_id,
        name=name,
        description=description,
        phase_count=phase_count,
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        last_run_at=latest.started_at if latest else None,
    )


async def _validated_directory_path(
    user_id: str,
    skill_id: str,
    directory_path: str | None,
    metadata: MetadataStore,
) -> Path:
    if not directory_path:
        raise ValueError("directory_path is required")
    skill_dir = Path(directory_path)
    if not skill_dir.is_absolute():
        _raise_invalid_directory_path(directory_path, "directory_path must be absolute")
    if not skill_dir.parent.exists():
        _raise_invalid_directory_path(directory_path, "directory_path parent must exist")

    resolved_skill_dir = skill_dir.resolve()
    for indexed_skill_id, entry in (await metadata.list_skill_index()).items():
        if indexed_skill_id == skill_id:
            continue
        if Path(entry["absolute_path"]).resolve() == resolved_skill_dir:
            response = error_response(
                error_code="SKILL_ALREADY_EXISTS",
                http_status=409,
                message=f"Directory path is already used by skill {indexed_skill_id}",
                details={"skill_id": indexed_skill_id, "directory_path": str(resolved_skill_dir)},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)
    for summary in await metadata.list_skills(user_id):
        if summary.id == skill_id or not summary.directory_path:
            continue
        if Path(summary.directory_path).resolve() == resolved_skill_dir:
            response = error_response(
                error_code="SKILL_ALREADY_EXISTS",
                http_status=409,
                message=f"Directory path is already used by skill {summary.id}",
                details={"skill_id": summary.id, "directory_path": str(resolved_skill_dir)},
                retry_strategy="not_retryable",
            )
            raise_error_response(response)
    return resolved_skill_dir


def _raise_invalid_directory_path(directory_path: str, message: str) -> None:
    response = error_response(
        error_code="INVALID_DIRECTORY_PATH",
        http_status=422,
        message=message,
        details={"directory_path": directory_path},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


def _detail_from_manifest(
    skill_id: str,
    skill_dir: Path,
    manifest: AgentSkillDef | GraphSkillDef | PersonaSkillDef,
    lint_result: LintResult,
) -> SkillDetail:
    return SkillDetail(
        manifest=manifest,
        file_paths={
            "skill_dir": str(skill_dir),
            "skill_md": str(skill_dir / "SKILL.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "predict_dir": str(predict_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        has_golden=_has_golden(skill_dir),
        latest_run_metadata=latest_run_metadata(skill_id),
        lint_result=lint_result,
    )


async def _detail_from_manifest_async(
    user_id: str,
    skill_id: str,
    skill_dir: Path,
    manifest: AgentSkillDef | GraphSkillDef | PersonaSkillDef,
    lint_result: LintResult,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    return SkillDetail(
        manifest=manifest,
        file_paths={
            "skill_dir": str(skill_dir),
            "skill_md": str(skill_dir / "SKILL.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "predict_dir": str(predict_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=latest,
        lint_result=lint_result,
    )


def _load_manifest(skill_path: Path) -> AgentSkillDef | GraphSkillDef | PersonaSkillDef:
    try:
        return SkillLoader().compile_skill(skill_path).manifest
    except Exception as exc:
        with contextlib.suppress(Exception):
            adapter: TypeAdapter[AgentSkillDef | GraphSkillDef | PersonaSkillDef] = TypeAdapter(
                SkillManifest,
            )
            return adapter.validate_python(_frontmatter(skill_path))
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message=str(exc),
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)


def _phase_summary_from_frontmatter(skill_path: Path) -> list[dict[str, Any]]:
    frontmatter = _frontmatter(skill_path)
    phases = frontmatter.get("phases")
    if isinstance(phases, list):
        return [
            {
                "name": str(phase.get("name", "")) if isinstance(phase, dict) else "",
                "tier": _phase_tier(phase),
                "has_validator": bool(phase.get("validator")) if isinstance(phase, dict) else False,
            }
            for phase in phases
        ]
    if frontmatter.get("type") == "agent":
        return [
            {
                "name": str(frontmatter.get("name") or ""),
                "tier": "agent",
                "has_validator": False,
            },
        ]
    return []


def _frontmatter(skill_path: Path) -> dict[str, Any]:
    raw = parse_skill_file(skill_path)["frontmatter"]
    return dict(raw)


def _phase_tier(phase: Any) -> str:
    if not isinstance(phase, dict):
        return ""
    return str(phase.get("llm_role") or phase.get("mode") or "")


def _phase_count_from_frontmatter(frontmatter: dict[str, Any]) -> int:
    phases = frontmatter.get("phases")
    if isinstance(phases, list):
        return len(phases)
    if frontmatter.get("type") == "agent":
        return 1
    return 0


def _has_golden(skill_dir: Path) -> bool:
    return golden_dir_for(skill_dir).exists()


def _sync_skill_index_entry(skill_id: str) -> dict[str, str] | None:
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


def _lint_error_from_issue(issue: CompileIssue) -> LintError:
    match = _LOCATION_RE.search(issue.location)
    line = int(match.group("line")) if match else None
    severity: Literal["error", "warning"] = "error" if issue.severity == "FATAL" else "warning"
    return LintError(
        line=line,
        column=None,
        error_code=issue.rule_id,
        severity=severity,
        message=issue.message,
        phase_name=_phase_from_location(match.group("loc") if match else None),
    )


def _phase_from_location(location: str | None) -> str | None:
    if not location:
        return None
    match = re.search(r"phases\.(\d+)", location)
    return f"phase[{match.group(1)}]" if match else None


def _raise_manifest_validation_failed(lint: LintResult) -> None:
    response = error_response(
        error_code="MANIFEST_VALIDATION_FAILED",
        http_status=422,
        message="Manifest validation failed",
        details={"errors": jsonable_encoder([error.model_dump() for error in lint.errors])},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


async def _list_skill_ids(root: Path, storage: StorageBackend) -> list[str]:
    skill_ids: list[str] = []
    for child_name in await storage.list_dirs(str(root)):
        if await storage.exists(str(root / child_name / "SKILL.md")):
            skill_ids.append(child_name)
    return sorted(skill_ids)


def _workspace_skills_dir_for(user_id: str) -> Path:
    return config.WORKSPACES_DIR / user_id / "skills"


def _rewrite_forked_skill_content(content: str, *, old_id: str, new_id: str) -> str:
    """Update frontmatter identity fields that exactly match the source id."""

    def replace_identity(match: re.Match[str]) -> str:
        value = match.group("value").strip()
        if value != old_id:
            return match.group(0)
        quote = match.group("quote")
        return f"{match.group('prefix')}{quote}{new_id}{quote}"

    rewritten = _ID_LINE_RE.sub(replace_identity, content)
    return _NAME_LINE_RE.sub(replace_identity, rewritten)


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.rglob("*"):
        target_path = target / source_path.relative_to(source)
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
