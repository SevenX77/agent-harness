"""Skill filesystem and graph_agent compile integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from graph_agent import compile_skill
from graph_agent.core.exceptions import GraphAgentError, SkillCompilationError, SkillLoadError
from graph_agent.core.graph_serializer import serialize_graph
from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import (
    GraphManifest,
    GraphPhaseRef,
    LogicNodeAST,
    SkillNodeAST,
    SubgraphNodeAST,
)

from app.core import config
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import LintError
from app.models.lint import LintResult
from app.models.runs import RunMetadata
from app.models.settings import AppSettings
from app.models.skills import (
    CompileError,
    CompileFailure,
    CompileSuccess,
    SerializeGraphReq,
    SerializeGraphRes,
    SkillDetail,
    SkillSummary,
)
from app.services.canvas_errors import CanvasConflictError, CanvasSerializerFatal
from app.services.config_arbitration import detect_config_mismatch
from app.services.file_watcher import record_api_write
from app.services.git_local import GitLocalService, initialize_skill_repository

_LOCATION_RE = re.compile(r":(?P<line>\d+)(?::(?P<loc>.*))?")
_NAME_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>name:\s*)(?P<quote>['\"]?)(?P<value>[^'\"\n]+)(?P=quote)\s*$"
)

_ALLOWED_SKILL_FILE_SUFFIXES = {".md", ".json", ".py"}
_PHASE_NODE_FILES = {"LOGIC.md", "SUBGRAPH.md", "SKILL.md"}
_SCAFFOLD_FILES = {
    "GRAPH.md": """---
schema_version: "2.1"
name: new-skill
description: "New Studio skill"
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="init" src="phases/init" depends_on="" />
""",
    "phases/init/LOGIC.md": """---
mode: logic
name: init
---
# init phase logic

Describe what this phase does.
""",
    "io/inputs.json": "{}\n",
    "io/outputs.json": "{}\n",
}


class CompileFailedError(Exception):
    """Raised when graph_agent compilation returns structured diagnostics."""

    def __init__(self, failure: CompileFailure) -> None:
        self.failure = failure
        super().__init__(failure.detail)


def validate_skill_file_path(rel_path: str) -> None:
    invalid_message = f"invalid_skill_file_path: {rel_path}"
    path = PurePosixPath(rel_path)
    parts = path.parts
    if (
        not rel_path
        or rel_path.startswith("/")
        or "\\" in rel_path
        or path.suffix not in _ALLOWED_SKILL_FILE_SUFFIXES
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise HTTPException(status_code=422, detail=invalid_message)
    if parts == ("GRAPH.md",):
        return
    if parts in {("io", "inputs.json"), ("io", "outputs.json")}:
        return
    if len(parts) == 2 and parts[0] == "tools" and parts[1].endswith(".py"):
        return
    if len(parts) == 3 and parts[0] == "phases" and parts[2] in _PHASE_NODE_FILES:
        return
    if (
        len(parts) == 4
        and parts[0] == "phases"
        and parts[2] in {"actions", "tools"}
        and parts[3].endswith(".py")
    ):
        return
    raise HTTPException(status_code=422, detail=invalid_message)


def write_skill_files_atomic(skill_dir: Path, files: dict[str, str]) -> None:
    for rel_path in files:
        validate_skill_file_path(rel_path)
    token = uuid.uuid4().hex
    tmp_dir = skill_dir.parent / f".{skill_dir.name}.tmp-{token}"
    backup_dir = skill_dir.parent / f".{skill_dir.name}.bak-{token}"
    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        for rel_path, content in files.items():
            target = tmp_dir.joinpath(*PurePosixPath(rel_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        lint = lint_skill_path(tmp_dir)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
        if skill_dir.exists():
            os.rename(skill_dir, backup_dir)
        os.rename(tmp_dir, skill_dir)
    except Exception:
        if not skill_dir.exists() and backup_dir.exists():
            os.rename(backup_dir, skill_dir)
        raise
    finally:
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)


def _scaffold_files_for(skill_id: str) -> dict[str, str]:
    files = dict(_SCAFFOLD_FILES)
    files["GRAPH.md"] = files["GRAPH.md"].replace("name: new-skill", f"name: {skill_id}")
    return files


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
    app_settings = await metadata.read_app_settings()
    local_git = GitLocalService()
    public_ids = await _list_skill_ids(config.SKILLS_DIR, storage)
    workspace_root = _workspace_skills_dir_for(user_id)
    workspace_ids = await _list_skill_ids(workspace_root, storage)
    metadata_summaries = await metadata.list_skills(user_id)
    for skill_id in public_ids:
        skill_dir = config.SKILLS_DIR / skill_id
        summaries[skill_id] = _attach_config_mismatch(
            await _summary_for_skill_dir_async(
                user_id,
                skill_dir,
                storage,
                metadata,
            ),
            skill_dir,
            app_settings,
            local_git,
        )
    for skill_id in workspace_ids:
        skill_dir = workspace_root / skill_id
        summaries[skill_id] = _attach_config_mismatch(
            await _summary_for_skill_dir_async(
                user_id,
                skill_dir,
                storage,
                metadata,
            ),
            skill_dir,
            app_settings,
            local_git,
        )
    for saved_summary in metadata_summaries:
        if not saved_summary.directory_path:
            continue
        skill_dir = Path(saved_summary.directory_path)
        summaries[saved_summary.id] = _attach_config_mismatch(
            (
                await _summary_for_skill_dir_async(
                    user_id,
                    skill_dir,
                    storage,
                    metadata,
                    skill_id=saved_summary.id,
                )
            ).model_copy(update={"directory_path": saved_summary.directory_path}),
            skill_dir,
            app_settings,
            local_git,
        )
    return sorted(summaries.values(), key=lambda summary: summary.id)


def _attach_config_mismatch(
    summary: SkillSummary,
    skill_dir: Path,
    app_settings: AppSettings,
    local_git: GitLocalService,
) -> SkillSummary:
    return summary.model_copy(
        update={
            "config_mismatch": detect_config_mismatch(
                summary.id,
                skill_dir,
                app_settings,
                local_git=local_git,
            ),
        },
    )


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
    lint = lint_result or lint_skill_path(skill_dir)
    if lint.status == "failed":
        return await _broken_detail_from_files_async(
            user_id,
            skill_id,
            skill_dir,
            lint,
            storage,
            metadata,
        )
    compiled = _load_compiled(skill_dir)
    return await _detail_from_manifest_async(
        user_id,
        skill_id,
        skill_dir,
        compiled,
        lint,
        storage,
        metadata,
    )


def lint_skill(skill_id: str) -> LintResult:
    """Lint a resolved skill by id."""
    return lint_skill_path(resolve_skill_dir(skill_id))


def lint_skill_path(skill_path: Path) -> LintResult:
    """Compile a V2.1 skill root into Studio lint diagnostics."""
    try:
        compiled = compile_skill(skill_path)
    except (SkillLoadError, SkillCompilationError) as exc:
        return LintResult(status="failed", errors=[_lint_error_from_exception(exc)])
    return LintResult(
        status="passed",
        errors=[],
        phases_summary=_phase_summary_from_compiled(compiled),
    )


async def compile_skill_for_studio(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> CompileSuccess:
    """Compile a resolved skill and return the Studio compile contract."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        compiled = compile_skill(skill_dir, cache=False)
    except (SkillLoadError, SkillCompilationError) as exc:
        raise CompileFailedError(_compile_failure_from_exception(exc, skill_dir)) from exc
    return CompileSuccess(
        skill_id=skill_id,
        status="ok",
        phase_count=len(compiled.manifest.phases),
        manifest_name=compiled.manifest.name,
    )


async def update_skill_content(
    user_id: str,
    skill_id: str,
    content: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    """Reject legacy single-file edits during the V2.1 backend cutover."""
    if not content.strip():
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message="Skill content must not be empty",
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    del user_id, skill_id, storage, metadata
    _raise_v21_directory_authoring_required()


async def update_skill_files(
    user_id: str,
    skill_id: str,
    files: dict[str, str],
    storage: StorageBackend,
    metadata: MetadataStore,
    *,
    expected_hash: str | None = None,
) -> SkillDetail:
    """Persist a full V2.1 skill file map and return the compiled detail."""
    if expected_hash is not None:
        current_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
        current_markdown = _read_current_graph_markdown(current_dir)
        current_hash = _graph_content_hash(current_markdown)
        if current_hash != expected_hash:
            raise CanvasConflictError(
                current_hash=current_hash,
                current_markdown_content=current_markdown,
            )
    skill_dir = await ensure_workspace_skill_dir_async(user_id, skill_id, storage, metadata)
    write_skill_files_atomic(skill_dir, files)
    for rel_path in files:
        record_api_write(skill_dir.joinpath(*PurePosixPath(rel_path).parts))
    lint = lint_skill_path(skill_dir)
    if lint.status == "failed":
        _raise_manifest_validation_failed(lint)
    compiled = _load_compiled(skill_dir)
    return await _detail_from_manifest_async(
        user_id,
        skill_id,
        skill_dir,
        compiled,
        lint,
        storage,
        metadata,
    )


async def update_skill_file(
    user_id: str,
    skill_id: str,
    rel_path: str,
    content: str,
    storage: StorageBackend,
    metadata: MetadataStore,
    *,
    expected_hash: str | None = None,
) -> str:
    validate_skill_file_path(rel_path)
    skill_dir = await ensure_workspace_skill_dir_async(user_id, skill_id, storage, metadata)
    target = skill_dir.joinpath(*PurePosixPath(rel_path).parts)
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    current_hash = _graph_content_hash(current)
    if expected_hash is not None and current_hash != expected_hash:
        raise CanvasConflictError(
            current_hash=current_hash,
            current_markdown_content=current,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    record_api_write(target)
    return _graph_content_hash(content)


async def delete_skill(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> None:
    """Delete a skill directory and clear all metadata for it."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    resolved_skill_dir = skill_dir.resolve()
    builtin_root = config.SKILLS_DIR.resolve()
    if resolved_skill_dir == builtin_root or resolved_skill_dir.is_relative_to(builtin_root):
        response = error_response(
            error_code="SKILL_READ_ONLY",
            http_status=403,
            message=f"Skill is read-only: {skill_id}",
            details={"skill_id": skill_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)

    await asyncio.to_thread(shutil.rmtree, resolved_skill_dir, ignore_errors=False)
    await metadata.remove_skill_index_entry(skill_id)
    await metadata.remove_skill_summary(user_id, skill_id)


async def create_new_skill(
    user_id: str,
    skill_id: str,
    files: dict[str, str],
    storage: StorageBackend,
    metadata: MetadataStore,
    directory_path: str | None = None,
) -> SkillSummary:
    """Create a new directory-based V2.1 skill."""
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
    if directory_path and await _directory_is_nonempty(skill_dir):
        summary = (
            await _summary_for_skill_dir_async(
                user_id,
                skill_dir,
                storage,
                metadata,
                skill_id=skill_id,
            )
        ).model_copy(
            update={"directory_path": str(skill_dir)},
        )
        await metadata.save_skill_index_entry(
            skill_id,
            {"absolute_path": str(skill_dir), "l2_remote_url": ""},
        )
        await metadata.save_skill_summary(user_id, summary)
        return summary

    skill_path = skill_dir / "GRAPH.md"
    public_path = config.SKILLS_DIR / skill_id / "GRAPH.md"
    if await storage.exists(str(skill_path)) or await storage.exists(str(public_path)):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    write_skill_files_atomic(skill_dir, files or _scaffold_files_for(skill_id))
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    initialize_skill_repository(skill_dir)
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
    target_path = target_dir / "GRAPH.md"
    public_collision = config.SKILLS_DIR / new_skill_id / "GRAPH.md"
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
        lint = lint_skill_path(target_dir)
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
        if await storage.exists(str(skill_dir / "GRAPH.md")):
            return skill_dir

    saved_summary = await metadata.get_skill_summary(user_id, skill_id)
    if saved_summary and saved_summary.directory_path:
        skill_dir = Path(saved_summary.directory_path)
        if await storage.exists(str(skill_dir / "GRAPH.md")):
            return skill_dir

    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await storage.exists(str(workspace_dir / "GRAPH.md")):
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if await storage.exists(str(public_dir / "GRAPH.md")):
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
        if await storage.exists(str(skill_dir)):
            return skill_dir

    saved_summary = await metadata.get_skill_summary(user_id, skill_id)
    if saved_summary and saved_summary.directory_path:
        skill_dir = Path(saved_summary.directory_path)
        if await storage.exists(str(skill_dir)):
            return skill_dir

    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await _workspace_skill_body_exists(workspace_dir, storage):
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if await storage.exists(str(public_dir)):
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
        if (skill_dir / "GRAPH.md").exists():
            return skill_dir

    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if _workspace_skill_body_exists_sync(workspace_dir):
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if (public_dir / "GRAPH.md").exists():
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
        if skill_dir.exists():
            return skill_dir

    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if _workspace_skill_body_exists_sync(workspace_dir):
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if public_dir.exists():
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
    return sorted(path for path in root.iterdir() if (path / "GRAPH.md").is_file())


def _summary_for_skill_dir(skill_dir: Path) -> SkillSummary:
    skill_id = skill_dir.name
    lint = lint_skill_path(skill_dir)
    if lint.status == "passed":
        compiled = _load_compiled(skill_dir)
        name = compiled.manifest.name
        description = str(compiled.manifest.description or "")
        phase_count = len(compiled.manifest.phases)
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
    if not await storage.exists(str(skill_dir / "GRAPH.md")):
        name = resolved_skill_id
        description = ""
        phase_count = 0
    elif (lint := lint_skill_path(skill_dir)).status == "passed":
        compiled = _load_compiled(skill_dir)
        name = compiled.manifest.name
        description = str(compiled.manifest.description or "")
        phase_count = len(compiled.manifest.phases)
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


async def _directory_is_nonempty(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    return await asyncio.to_thread(lambda: any(path.iterdir()))


async def _workspace_skill_body_exists(path: Path, storage: StorageBackend) -> bool:
    if not await storage.exists(str(path)):
        return False
    child_names = await storage.list_dirs(str(path))
    files = await asyncio.to_thread(
        lambda: (
            [child.name for child in path.iterdir() if child.is_file()] if path.exists() else []
        ),
    )
    entries = set(child_names) | set(files)
    return not entries or bool(entries - {"runs", "skill_summary.json"})


def _workspace_skill_body_exists_sync(path: Path) -> bool:
    if not path.exists():
        return False
    entries = {child.name for child in path.iterdir()}
    return not entries or bool(entries - {"runs", "skill_summary.json"})


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
    compiled: CompiledSkill,
    lint_result: LintResult,
) -> SkillDetail:
    return SkillDetail(
        manifest=compiled.manifest,
        graph_topology=_graph_topology(compiled),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "predict_dir": str(predict_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        files=_read_skill_files(skill_dir),
        has_golden=_has_golden(skill_dir),
        latest_run_metadata=latest_run_metadata(skill_id),
        lint_result=lint_result,
        manifest_errors=[],
    )


async def _detail_from_manifest_async(
    user_id: str,
    skill_id: str,
    skill_dir: Path,
    compiled: CompiledSkill,
    lint_result: LintResult,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    return SkillDetail(
        manifest=compiled.manifest,
        graph_topology=_graph_topology(compiled),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "predict_dir": str(predict_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=latest,
        lint_result=lint_result,
        manifest_errors=[],
    )


async def _broken_detail_from_files_async(
    user_id: str,
    skill_id: str,
    skill_dir: Path,
    lint_result: LintResult,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    return SkillDetail(
        manifest=GraphManifest(name=skill_id, description="(broken: manifest invalid)", phases=[]),
        graph_topology=[],
        node_schema_v21=_node_schema_v21(),
        io_schema={},
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "predict_dir": str(predict_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        # Broken/V1 details still expose the real asset tree for the Explorer panel.
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=latest,
        lint_result=lint_result,
        manifest_errors=lint_result.errors,
    )


def _read_skill_files(skill_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(skill_dir).as_posix()
        parts = path.relative_to(skill_dir).parts
        if any(part.startswith(".") or part in {"__pycache__", "node_modules"} for part in parts):
            continue
        if path.stat().st_size > 1024 * 1024:
            files[rel_path] = "(binary or too large)"
            continue
        try:
            files[rel_path] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return files


def _read_current_graph_markdown(skill_dir: Path) -> str:
    graph_path = skill_dir / "GRAPH.md"
    if not graph_path.exists():
        return ""
    return graph_path.read_text(encoding="utf-8")


def _graph_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_compiled(skill_path: Path) -> CompiledSkill:
    try:
        return SkillLoader().compile_skill(skill_path)
    except Exception as exc:
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message=str(exc),
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)


def _load_compiled_for_graph_serializer(skill_path: Path) -> CompiledSkill:
    try:
        return SkillLoader(validate_context_writes=False).compile_skill(skill_path)
    except Exception as exc:
        response = error_response(
            error_code="MANIFEST_VALIDATION_FAILED",
            http_status=422,
            message=str(exc),
            details={"errors": []},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)


async def serialize_skill_graph_markdown(
    user_id: str,
    skill_id: str,
    request: SerializeGraphReq,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SerializeGraphRes:
    """Serialize a Canvas topology snapshot against the latest on-disk GRAPH.md."""
    started = time.perf_counter()
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    graph_path = skill_dir / "GRAPH.md"
    original_md = await storage.read_text(str(graph_path))
    current_hash = _graph_content_hash(original_md)
    try:
        compiled = _load_compiled_for_graph_serializer(skill_dir)
        if request.expected_hash is not None and request.expected_hash != current_hash:
            raise CanvasConflictError(
                current_hash=current_hash,
                current_markdown_content=original_md,
                current_phase_count=len(compiled.manifest.phases),
            )
        _validate_canvas_topology(request)
        manifest = compiled.manifest.model_copy(
            update={
                "phases": [
                    GraphPhaseRef(
                        id=phase.id,
                        src=phase.src,
                        depends_on=list(phase.depends_on),
                    )
                    for phase in request.phases
                ]
            }
        )
        markdown = serialize_graph(GraphManifest.model_validate(manifest.model_dump()), original_md)
    except CanvasConflictError:
        raise
    except CanvasSerializerFatal as exc:
        exc.elapsed_ms = (time.perf_counter() - started) * 1000
        raise
    except (GraphAgentError, SkillLoadError, SkillCompilationError) as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise _serializer_fatal_from_engine_error(exc, elapsed_ms) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    return SerializeGraphRes(
        markdown_content=markdown,
        phase_count=len(request.phases),
        elapsed_ms=elapsed_ms,
        current_hash=current_hash,
    )


def _validate_canvas_topology(request: SerializeGraphReq) -> None:
    phase_ids = {phase.id for phase in request.phases}
    for phase in request.phases:
        for dep in phase.depends_on:
            if dep not in phase_ids:
                raise CanvasSerializerFatal(
                    code="serializer_orphan",
                    message=f"phase {phase.id!r} depends_on unknown phase {dep!r}",
                    detail={"phase_id": phase.id, "dependency": dep},
                )
            if dep == phase.id:
                raise CanvasSerializerFatal(
                    code="serializer_cycle",
                    message=f"phase {phase.id!r} cannot depend on itself",
                    detail={"phase_id": phase.id},
                )
    _validate_canvas_acyclic(request)
    _validate_canvas_connected(request)


def _validate_canvas_acyclic(request: SerializeGraphReq) -> None:
    adjacency: dict[str, list[str]] = {phase.id: [] for phase in request.phases}
    for phase in request.phases:
        for dep in phase.depends_on:
            adjacency[dep].append(phase.id)
    state: dict[str, str] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        state[node] = "gray"
        stack.append(node)
        for nxt in adjacency[node]:
            if state.get(nxt) == "gray":
                start = stack.index(nxt)
                cycle = stack[start:] + [nxt]
                raise CanvasSerializerFatal(
                    code="serializer_cycle",
                    message="cycle detected: " + " -> ".join(cycle),
                    detail={"cycle": cycle},
                )
            if state.get(nxt) is None:
                visit(nxt)
        stack.pop()
        state[node] = "black"

    for node in adjacency:
        if state.get(node) is None:
            visit(node)


def _validate_canvas_connected(request: SerializeGraphReq) -> None:
    if len(request.phases) <= 1:
        return
    adjacency: dict[str, set[str]] = {phase.id: set() for phase in request.phases}
    for phase in request.phases:
        for dep in phase.depends_on:
            adjacency[phase.id].add(dep)
            adjacency[dep].add(phase.id)
    start = request.phases[0].id
    visited: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(sorted(adjacency[node] - visited))
    for phase in request.phases:
        if phase.id not in visited:
            raise CanvasSerializerFatal(
                code="serializer_orphan",
                message=f"orphan phase {phase.id!r} is disconnected from the main graph",
                detail={"phase_id": phase.id},
            )


def _serializer_fatal_from_engine_error(exc: Exception, elapsed_ms: float) -> CanvasSerializerFatal:
    message = str(exc)
    code = "serializer_invalid_topology"
    if "cycle detected" in message or "cannot depend on itself" in message:
        code = "serializer_cycle"
    elif "unknown phase" in message or "orphan phase" in message:
        code = "serializer_orphan"
    return CanvasSerializerFatal(
        code=code,
        message=message,
        detail={"engine_error": exc.__class__.__name__},
        elapsed_ms=elapsed_ms,
    )


def _phase_summary_from_compiled(compiled: CompiledSkill) -> list[dict[str, Any]]:
    mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
    return [
        {
            "name": phase.id,
            "tier": mode_by_phase.get(phase.id, ""),
            "has_validator": False,
        }
        for phase in compiled.manifest.phases
    ]


def _graph_topology(compiled: CompiledSkill) -> list[dict[str, object]]:
    mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
    return [
        {
            "id": phase.id,
            "src": phase.src,
            "depends_on": list(phase.depends_on),
            "mode": mode_by_phase.get(phase.id, ""),
        }
        for phase in compiled.manifest.phases
    ]


def _node_schema_v21() -> dict[str, dict[str, object]]:
    return {
        "graph_phase_ref": GraphPhaseRef.model_json_schema(),
        "logic": LogicNodeAST.model_json_schema(),
        "skill": SkillNodeAST.model_json_schema(),
        "subgraph": SubgraphNodeAST.model_json_schema(),
    }


def _io_schema(compiled: CompiledSkill) -> dict[str, dict[str, object]]:
    return {
        "inputs": dict(compiled.raw["io"]["inputs"]),
        "outputs": dict(compiled.raw["io"]["outputs"]),
    }


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


def _lint_error_from_exception(exc: Exception) -> LintError:
    message = str(exc)
    match = _LOCATION_RE.search(message)
    line = int(match.group("line")) if match else None
    return LintError(
        file=_file_from_error_message(message),
        line=line,
        column=None,
        error_code=_error_code_from_message(message),
        severity="error",
        message=message,
        phase_name=_phase_from_location(match.group("loc") if match else None),
    )


def _file_from_error_message(message: str) -> str | None:
    for candidate in ("GRAPH.md", "io/inputs.json", "io/outputs.json"):
        if candidate in message:
            return candidate
    phase_match = re.search(r"(phases/[A-Za-z0-9_-]+/(?:LOGIC|SUBGRAPH|SKILL)\.md)", message)
    return phase_match.group(1) if phase_match else None


def _compile_failure_from_exception(exc: Exception, skill_dir: Path) -> CompileFailure:
    errors = _compile_errors_from_exception(exc, skill_dir)
    count = len(errors)
    noun = "error" if count == 1 else "errors"
    return CompileFailure(
        detail=f"Skill compilation failed with {count} {noun}",
        errors=errors,
    )


def _compile_errors_from_exception(exc: Exception, skill_dir: Path) -> list[CompileError]:
    compile_result = getattr(exc, "compile_result", None)
    issues = getattr(compile_result, "issues", None)
    if isinstance(issues, list) and issues:
        return [_compile_error_from_issue(issue, skill_dir) for issue in issues]
    return [_compile_error_from_exception(exc, skill_dir)]


def _compile_error_from_issue(issue: object, skill_dir: Path) -> CompileError:
    location = getattr(issue, "location", None)
    line = None
    file_path = None
    field = None
    if isinstance(location, str):
        file_path, line, field = _parse_compile_location(location, skill_dir)
    severity = str(getattr(issue, "severity", "fatal")).lower()
    return CompileError(
        file=file_path,
        line=line,
        field=field,
        severity="warning" if severity == "warning" else "fatal",
        message=str(getattr(issue, "message", "Skill compilation failed")),
    )


def _compile_error_from_exception(exc: Exception, skill_dir: Path) -> CompileError:
    message = str(exc)
    match = _LOCATION_RE.search(message)
    line = getattr(exc, "line", None)
    if line is None and match:
        line = int(match.group("line"))
    file_path = _relative_compile_path(getattr(exc, "skill_path", None), skill_dir)
    if file_path is None:
        file_path = _file_from_error_message(message)
    return CompileError(
        file=file_path,
        line=line,
        field=getattr(exc, "field_path", None),
        severity="fatal",
        message=message,
    )


def _parse_compile_location(
    location: str,
    skill_dir: Path,
) -> tuple[str | None, int | None, str | None]:
    file_part = location
    field = None
    if ":" in location:
        file_part, rest = location.split(":", 1)
        line_match = re.match(r"(?P<line>\d+)(?::(?P<field>.*))?", rest)
        if line_match:
            return (
                _relative_compile_path(Path(file_part), skill_dir) or file_part or None,
                int(line_match.group("line")),
                line_match.group("field") or None,
            )
        field = rest or None
    return _relative_compile_path(Path(file_part), skill_dir) or file_part or None, None, field


def _relative_compile_path(path: str | os.PathLike[str] | None, skill_dir: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.relative_to(skill_dir).as_posix()
    except ValueError:
        return candidate.as_posix() if not candidate.is_absolute() else candidate.name


def _phase_from_location(location: str | None) -> str | None:
    if not location:
        return None
    match = re.search(r"phases\.(\d+)", location)
    return f"phase[{match.group(1)}]" if match else None


def _error_code_from_message(message: str) -> str:
    match = re.search(r"\[(F-[^\]]+)\]", message)
    return match.group(1) if match else "F-v21-compile"


def _raise_v21_directory_authoring_required() -> NoReturn:
    response = error_response(
        error_code="MANIFEST_VALIDATION_FAILED",
        http_status=422,
        message=(
            "V2.1 skills are directory-based; single-file SKILL.md authoring "
            "is not supported by this endpoint"
        ),
        details={"required_entry": "GRAPH.md"},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


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
        if child_name.startswith(".") or child_name == "__pycache__":
            continue
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
