"""Skill filesystem and graph_agent compile integration."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from graph_agent import CompiledSkill, compile_skill
from graph_agent.core.exceptions import SkillCompilationError, SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import GraphPhaseRef, LogicNodeAST, SkillNodeAST, SubgraphNodeAST

from app.core import config
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import LintError
from app.models.lint import LintResult
from app.models.runs import RunMetadata
from app.models.skills import SkillDetail, SkillSummary

_LOCATION_RE = re.compile(r":(?P<line>\d+)(?::(?P<loc>.*))?")
_NAME_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>name:\s*)(?P<quote>['\"]?)(?P<value>[^'\"\n]+)(?P=quote)\s*$"
)
_ID_LINE_RE = re.compile(
    r"(?m)^(?P<prefix>id:\s*)(?P<quote>['\"]?)(?P<value>[^'\"\n]+)(?P=quote)\s*$"
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


def validate_skill_file_path(rel_path: str) -> None:
    """Validate V2.1 authoring file paths before reading or writing skill files."""
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
    """Replace a V2.1 skill directory using tmpdir-rename swap with rollback."""
    for rel_path in files:
        validate_skill_file_path(rel_path)

    token = uuid4().hex
    tmp_dir = skill_dir.parent / f".{skill_dir.name}.tmp-{token}"
    backup_dir = skill_dir.parent / f".{skill_dir.name}.bak-{token}"

    try:
        tmp_dir.mkdir(parents=True, exist_ok=False)
        for rel_path, content in files.items():
            target = tmp_dir.joinpath(*PurePosixPath(rel_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

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


def ensure_workspace_layout() -> None:
    """Create the writable Studio workspace skeleton."""
    config.default_workspace_skills_dir().mkdir(parents=True, exist_ok=True)


async def list_skill_summaries(
    user_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> list[SkillSummary]:
    """Return public and workspace skills, with workspace copies taking precedence."""
    summaries: dict[str, SkillSummary] = {}
    public_ids = await _list_skill_ids(config.SKILLS_DIR, storage)
    workspace_root = _workspace_skills_dir_for(user_id)
    workspace_ids = await _list_skill_ids(workspace_root, storage)
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
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage)
    lint = lint_result or lint_skill_path(skill_dir)
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
        status="passed", errors=[], phases_summary=_phase_summary_from_compiled(compiled)
    )


async def update_skill_content(
    user_id: str,
    skill_id: str,
    content: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> NoReturn:
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
) -> SkillDetail:
    """Persist a full V2.1 skill file map and return the compiled detail."""
    skill_dir = await ensure_workspace_skill_dir_async(user_id, skill_id, storage)
    write_skill_files_atomic(skill_dir, files)
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


async def create_new_skill(
    user_id: str,
    skill_id: str,
    files: dict[str, str],
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillSummary:
    """Create a new workspace skill from the built-in V2.1 starter scaffold."""
    del files
    public_path = config.SKILLS_DIR / skill_id / "GRAPH.md"
    workspace_path = _workspace_skills_dir_for(user_id) / skill_id / "GRAPH.md"
    if await storage.exists(str(workspace_path)) or await storage.exists(str(public_path)):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    skill_dir = _workspace_skills_dir_for(user_id) / skill_id
    write_skill_files_atomic(skill_dir, _scaffold_files_for(skill_id))
    summary = await _summary_for_skill_dir_async(user_id, skill_dir, storage, metadata)
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

    source_dir = await resolve_skill_dir_async(user_id, skill_id, storage)
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
) -> Path:
    """Return a writable skill dir, forking a public skill into workspace if needed."""
    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await storage.exists(str(workspace_dir / "GRAPH.md")):
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if not await storage.exists(str(public_dir / "GRAPH.md")):
        raise standard_http_exception(
            "SKILL_NOT_FOUND",
            f"Skill not found: {skill_id}",
            {"skill_id": skill_id},
        )
    await storage.copy_tree(str(public_dir), str(workspace_dir))
    return workspace_dir


async def resolve_skill_dir_async(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
) -> Path:
    """Resolve a skill id through storage, preferring workspace copies."""
    workspace_dir = _workspace_skills_dir_for(user_id) / skill_id
    if await storage.exists(str(workspace_dir / "GRAPH.md")):
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if await storage.exists(str(public_dir / "GRAPH.md")):
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
    """Return a writable skill dir, forking a public skill into workspace if needed."""
    ensure_workspace_layout()
    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if (workspace_dir / "GRAPH.md").exists():
        return workspace_dir

    public_dir = config.SKILLS_DIR / skill_id
    if not (public_dir / "GRAPH.md").exists():
        raise standard_http_exception(
            "SKILL_NOT_FOUND",
            f"Skill not found: {skill_id}",
            {"skill_id": skill_id},
        )
    _copy_tree(public_dir, workspace_dir)
    return workspace_dir


def resolve_skill_dir(skill_id: str) -> Path:
    """Resolve a skill id, preferring writable workspace copies."""
    workspace_dir = config.default_workspace_skills_dir() / skill_id
    if (workspace_dir / "GRAPH.md").exists():
        return workspace_dir
    public_dir = config.SKILLS_DIR / skill_id
    if (public_dir / "GRAPH.md").exists():
        return public_dir
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


def run_dir_for(skill_id: str, run_id: str) -> Path:
    """Return the Studio V3 run directory for a skill run."""
    return config.default_workspace_skills_dir() / skill_id / "runs" / run_id


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
    runs_dir = config.default_workspace_skills_dir() / skill_id / "runs"
    if not runs_dir.exists():
        return None
    candidates: list[RunMetadata] = []
    for metadata_path in runs_dir.glob("*/run_metadata.json"):
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
) -> SkillSummary:
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
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    return SkillSummary(
        id=skill_id,
        name=name,
        description=description,
        phase_count=phase_count,
        has_golden=await storage.exists(str(skill_dir / "golden")),
        last_run_at=latest.started_at if latest else None,
    )


def _detail_from_manifest(
    skill_id: str,
    skill_dir: Path,
    compiled: CompiledSkill,
    lint_result: LintResult,
) -> SkillDetail:
    workspace_skill_dir = config.default_workspace_skills_dir() / skill_id
    return SkillDetail(
        manifest=compiled.manifest,
        graph_topology=_graph_topology(compiled),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(workspace_skill_dir / "runs"),
            "test_inputs_dir": str(workspace_skill_dir / "test_inputs"),
            "golden_dir": str(workspace_skill_dir / "golden"),
        },
        files=_read_skill_files(skill_dir),
        has_golden=_has_golden(skill_dir),
        latest_run_metadata=latest_run_metadata(skill_id),
        lint_result=lint_result,
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
    workspace_skill_dir = _workspace_skills_dir_for(user_id) / skill_id
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    return SkillDetail(
        manifest=compiled.manifest,
        graph_topology=_graph_topology(compiled),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(workspace_skill_dir / "runs"),
            "test_inputs_dir": str(workspace_skill_dir / "test_inputs"),
            "golden_dir": str(workspace_skill_dir / "golden"),
        },
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(skill_dir / "golden")),
        latest_run_metadata=latest,
        lint_result=lint_result,
    )


def _read_skill_files(skill_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(skill_dir).as_posix()
        try:
            validate_skill_file_path(rel_path)
        except HTTPException:
            continue
        files[rel_path] = path.read_text(encoding="utf-8")
    return files


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


def _has_golden(skill_dir: Path) -> bool:
    return (skill_dir / "golden").exists()


def _lint_error_from_exception(exc: Exception) -> LintError:
    message = str(exc)
    match = _LOCATION_RE.search(message)
    line = int(match.group("line")) if match else None
    return LintError(
        line=line,
        column=None,
        error_code=_error_code_from_message(message),
        severity="error",
        message=message,
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
        if await storage.exists(str(root / child_name / "GRAPH.md")):
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


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.rglob("*"):
        target_path = target / source_path.relative_to(source)
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
