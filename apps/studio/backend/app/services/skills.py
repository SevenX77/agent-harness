"""Skill filesystem and graph_agent compile integration."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from app.core import config
from app.core.adapters.atomic_file import (
    read_published_text,
    write_bytes_atomically,
    write_text_atomically,
)
from app.core.adapters.engine import (
    AgentNodeAST,
    CompiledSkill,
    GraphAgentError,
    GraphCompileError,
    GraphManifest,
    GraphPhaseRef,
    GraphTopologySerializationError,
    LogicNodeAST,
    ResourceNotFoundError,
    SkillLoader,
    SubgraphNodeAST,
    SubgraphTopologyProjectionError,
    compile_skill,
    load_child_graph_topology_projection,
    load_graph_topology_projection,
    parse_markdown_parts,
    read_subgraph_path,
)
from app.core.adapters.run_layout import predicts_root, runs_root
from app.core.adapters.transport_factory import build_engine_adapter
from app.core.authored_text import read_authored_text
from app.core.exceptions import error_response, raise_error_response, standard_http_exception
from app.core.path_containment import PathEscapesDirectory, resolve_within_roots
from app.core.ports.metadata import MetadataStore
from app.core.ports.storage import StorageBackend
from app.models.errors import LintError
from app.models.lint import LintResult
from app.models.runs import RunMetadata
from app.models.skills import (
    ChildGraphTopology,
    CompileError,
    CompileFailure,
    CompileSuccess,
    SerializeGraphReq,
    SerializeGraphRes,
    SkillDetail,
    SkillSummary,
)
from app.services.canvas_data_gap import build_phase_io_index, compute_field_supply
from app.services.canvas_errors import CanvasConflictError, CanvasSerializerFatal
from app.services.file_watcher import record_api_write, register_workspace
from app.services.gate_events import publish_skill_gate
from app.services.git_local import initialize_skill_repository
from app.services.graph_roundtrip import serialize_graph_topology_from_markdown
from app.services.run_ids import is_predict_run_id
from app.services.runtime_config import refresh_runtime_config, runtime_input_fields_for_engine
from app.services.skill_resolver import build_studio_skill_resolver

logger = logging.getLogger(__name__)

_LOCATION_RE = re.compile(r":(?P<line>\d+)(?::(?P<loc>.*))?")
_SAFE_SKILL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._:-]*$")
_ALLOWED_SKILL_FILE_SUFFIXES = {".md", ".json", ".py"}
_PHASE_NODE_FILES = {"LOGIC.md", "SUBGRAPH.md", "SKILL.md"}
_SCAFFOLD_FILES = {
    "GRAPH.md": """---
schema_version: "v0.3.0"
name: new-skill
description: "New Studio skill"
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - init
---
<phase depends_on="input" output>init</phase>
""",
    "phases/init/SKILL.md": """---
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
tools: []
max_iterations: 10
---
<role>TODO: describe who this agent is.</role>
<goal>TODO: describe what this agent should produce.</goal>

<step id="S1" name="todo">TODO: describe the first step.</step>

<protocol id="P1">TODO: describe a rule the agent must follow.</protocol>
""",
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
    if len(parts) == 4 and parts[0] == "phases" and parts[2] in {"actions", "tools"} and parts[3].endswith(".py"):
        return
    raise HTTPException(status_code=422, detail=invalid_message)


def write_skill_files_atomic(skill_dir: Path, files: dict[str, str]) -> None:
    """Publish ``files`` into ``skill_dir``, or leave the directory as it was.

    The unit of replacement is the declared file, never the directory. Only the
    paths ``validate_skill_file_path`` admits can appear in ``files``, so
    ``.git/``, ``.workspace/`` and ``subgraph/`` are structurally unable to be
    submitted — and swapping the directory for one built out of ``files`` would
    delete exactly those. ``rsync`` draws the same line: it overwrites what the
    source carries and removes the rest only when the caller asks for it with
    ``--delete``. This API has no way to express "and remove the rest", so it
    removes nothing.

    Validation runs against ``skill_dir`` itself once the files are in place,
    because the compiler has to judge the skill it will actually load. Judging a
    directory built from ``files`` alone judges a skill root missing whatever
    the payload could not carry — a graph with a subgraph phase can never pass
    such a check, no matter how correct the skill on disk is.

    A rejected batch is undone from the previous bytes captured below: the shape
    ``dpkg`` uses when it moves the old file aside before unpacking the new one,
    so a failed unpack can put the old one back. What is NOT borrowed is any
    crash-time guarantee — ``dpkg`` has a journal and this does not. If the
    process dies mid-batch, some files are new and some are old and a stray
    ``.<name>.*.tmp`` may remain; nothing outside ``files`` is lost, and the
    recovery is to save again, the same idempotent-rerun recovery ``rsync``
    relies on.
    """
    for rel_path in files:
        validate_skill_file_path(rel_path)
    targets = {rel_path: skill_dir.joinpath(*PurePosixPath(rel_path).parts) for rel_path in files}
    previous_bytes = {target: (target.read_bytes() if target.is_file() else None) for target in targets.values()}
    created_directories = _directories_this_write_creates(skill_dir, targets.values())
    published: list[Path] = []
    try:
        for rel_path, target in targets.items():
            write_text_atomically(target, files[rel_path])
            published.append(target)
        # Structure-only gate: role governance is a diagnostics-surface concern
        # (see lint_skill_path docstring / J-X.10) — gating writes on it would
        # make the role-unset scaffold uncreatable.
        lint = lint_skill_path(skill_dir, include_studio_preflight=False, include_role_governance=False)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
    except Exception:
        _restore_previous_bytes(published, previous_bytes)
        if skill_dir in created_directories:
            # Nothing was here before this call, so removing everything the
            # failed write and its lint left behind removes only our own work.
            _rmtree_with_retry(skill_dir)
        else:
            _remove_empty_directories(created_directories)
        raise


def _directories_this_write_creates(skill_dir: Path, targets: Iterable[Path]) -> set[Path]:
    """The directories that do not exist yet, so a rollback can take them back.

    A rejected write must not leave an empty ``phases/<new-id>/`` behind: an
    empty phase directory is itself a compile defect, so "changed nothing" has
    to cover directories as well as files.
    """
    missing: set[Path] = set()
    for target in targets:
        directory = target.parent
        while not directory.exists() and directory not in missing:
            missing.add(directory)
            if directory == skill_dir:
                break
            directory = directory.parent
    return missing


def _restore_previous_bytes(published: Iterable[Path], previous_bytes: dict[Path, bytes | None]) -> None:
    for target in published:
        before = previous_bytes[target]
        if before is None:
            target.unlink(missing_ok=True)
        else:
            write_bytes_atomically(target, before)


def _remove_empty_directories(directories: Iterable[Path]) -> None:
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            # Still holds something, which by construction is not ours: this
            # write only ever created the directory, never its other contents.
            pass


def _rmtree_with_retry(path: Path, *, attempts: int = 20, delay_seconds: float = 0.05) -> None:
    for attempt in range(attempts):
        try:
            _rmtree_once(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)


def _rmtree_once(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_rmtree_chmod_and_retry)
    else:
        shutil.rmtree(path, onerror=_rmtree_chmod_and_retry)


def _rmtree_chmod_and_retry(function: Any, path: str, _excinfo: object) -> None:
    try:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
    except OSError:
        pass
    function(path)


def _scaffold_files_for(skill_id: str) -> dict[str, str]:
    files = dict(_SCAFFOLD_FILES)
    files["GRAPH.md"] = files["GRAPH.md"].replace("name: new-skill", f"name: {skill_id}")
    return files


def ensure_workspace_layout() -> None:
    """Create the writable Studio app-data skeleton."""
    config.DEFAULT_SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
    config.WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_skill_git_repo(skill_dir: Path) -> None:
    """Auto-init L1 git the first time a skill is opened.

    skill-repo-git-model: a skill IS a standalone git repo. Opening one with no
    ``.git`` yet
    turns it into its own repo — Local History then shows THIS skill's history
    history instead of an enclosing repo's history. No-op once ``.git`` exists.
    """
    if (skill_dir / ".git").exists():
        return
    initialize_skill_repository(skill_dir)


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
    # Opening a skill makes it a standalone git repo: init L1 git here on first
    # open of a writable user skill so Local History reflects THIS skill's own
    # history, not an enclosing repo's. Idempotent; skips bundled read-only skills.
    _ensure_skill_git_repo(skill_dir)
    # Follow whatever the user opens: watch this skill's actual directory (from any
    # path), not just the app's built-in skills dirs, so external file changes push
    # live skill_changed events. Idempotent — a no-op once already watched.
    register_workspace(skill_dir, skill_id)
    lint = lint_result or lint_skill_path(skill_dir)
    if lint.status == "failed" and lint.phases_summary is None:
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


def lint_skill_on_disk(skill_id: str, workspace_root: str | None = None) -> LintResult:
    """Lint the ON-DISK skill tree (03_compile A13: canvas-write relint).

    A canvas topology write (connect / disconnect / delete phase) settles to
    disk before the relint fires, so the disk tree IS the source truth — no
    markdown body round-trip. ``workspace_root`` points at the skill dir for
    workspace-based skills; without it the skill resolves from the global store.
    """
    if workspace_root:
        root = _requested_workspace_root_or_none(skill_id, workspace_root)
        if root is not None:
            return lint_skill_path(root)
    return lint_skill(skill_id)


def lint_skill_path(
    skill_path: Path,
    *,
    include_studio_preflight: bool = True,
    include_role_governance: bool = True,
) -> LintResult:
    """Compile a V2.1 skill root into Studio lint diagnostics.

    ``include_role_governance=False`` lints structure only (``allowed_roles``
    stays None, so the engine skips the role checks). The write seams use it:
    whether a role resolves depends on llm_roles.yaml — host config OUTSIDE the
    tree that can change without any file write — so a write gate cannot keep
    the tree role-consistent, it can only refuse legitimate states. J-X.10
    (用户裁决 2026-08-31) makes one such state first-class: a fresh skill is
    created with NO role and the compile diagnostic [F-v3-agent-llm-role-missing]
    IS the guidance to set one. Diagnostics surfaces keep full governance.
    """
    runtime_config = refresh_runtime_config(skill_path)
    try:
        compiled = compile_skill(
            skill_path,
            skill_resolver=build_studio_skill_resolver(),
            runtime_input_fields=runtime_input_fields_for_engine(runtime_config),
            allowed_roles=_configured_role_names() if include_role_governance else None,
        )
    except (GraphCompileError, ResourceNotFoundError) as exc:
        # compile-lint F6: lint projects the engine's FULL aggregated defect set
        # (same seam the manual Compile drawer expands), never just the primary.
        errors = _lint_errors_from_exception(exc, skill_path)
        if include_studio_preflight:
            errors.extend(
                _lint_error_from_compile_error(error)
                for error in _runtime_input_preflight_errors_from_graph_frontmatter(
                    skill_path,
                    runtime_config,
                )
            )
        return LintResult(status="failed", errors=errors)
    # Studio-layer config-consistency check layered on a successful compile: the engine
    # treats llm_role as an opaque string (it does not know about gateway roles), so
    # "role not configured" is surfaced here as a NON-FATAL warning on the llm_role field
    # — compile still passes; the Properties panel / node badge / editor underline light
    # up from this same diagnostic.
    role_warnings = []
    preflight_errors = (
        _studio_preflight_lint_errors(compiled, skill_path, runtime_config) if include_studio_preflight else []
    )
    return LintResult(
        status="failed" if any(error.severity == "error" for error in preflight_errors) else "passed",
        errors=[*role_warnings, *preflight_errors],
        phases_summary=_phase_summary_from_compiled(compiled),
    )


def _studio_preflight_lint_errors(
    compiled: CompiledSkill,
    skill_dir: Path,
    runtime_config: dict[str, Any],
) -> list[LintError]:
    """Mirror Compile's Studio-owned preflight gates into first-screen/realtime lint."""
    compile_errors = [
        *_validate_runtime_inputs_against_graph_input_schema(compiled, runtime_config),
        *_validate_golden_against_output_schema(skill_dir.name, str(skill_dir)),
        *_validate_manifest_name_is_the_registered_id(compiled.manifest.name, skill_dir),
    ]
    return [_lint_error_from_compile_error(error) for error in compile_errors]


def _validate_manifest_name_is_the_registered_id(
    manifest_name: str,
    skill_dir: Path,
) -> list[CompileError]:
    """Warn when a skill answers "who am I" two different ways.

    A skill has two identities: the key it is registered under in
    ``skill_index.json`` (derived from the directory name by the Rust writer,
    ``native_fs.rs`` ``skill_id_from_workspace_root``) and the ``name:`` in its
    GRAPH.md frontmatter. Nothing ever compared them, so copying a skill
    directory — which does not rewrite ``name:`` — leaves the copy advertising
    the SOURCE skill's id. An agent reading the open GRAPH.md then addresses the
    wrong skill (2026-08-15 incident; the structural half of that fix is
    ``services/copilot_skill_binding.py``, this is the half that makes the
    ambiguity visible to the human).

    The index is Studio's own registry — the engine has never heard of it — so
    this is a Studio-owned preflight check, not an engine compile rule (AGENTS.md
    "Compile/lint 单出口"). It is a WARNING: a registry hygiene problem is not a
    graph defect and must not block compiling. Directories that are not in the
    index at all stay silent: realtime lint compiles a throwaway sandbox copy in
    the OS temp dir, and a diagnostic on every keystroke there would be noise
    about a directory the user never opened.
    """

    registered_id = registered_skill_id_for_dir(skill_dir)
    if registered_id is None or manifest_name == registered_id:
        return []
    return [
        CompileError(
            file="GRAPH.md",
            line=_frontmatter_name_line(skill_dir),
            field="name",
            severity="warning",
            message=(
                f"GRAPH.md says name: {manifest_name}, but this folder is open in Studio as "
                f"{registered_id!r}. Studio resolves {manifest_name!r} to a different skill, so "
                f"anything addressing this skill by its manifest name edits that other skill. "
                f"Rename it to {registered_id!r}."
            ),
            error_code="STUDIO_MANIFEST_NAME_NOT_REGISTERED_ID",
        )
    ]


def _frontmatter_name_line(skill_dir: Path) -> int | None:
    """1-based line of the frontmatter ``name:`` key, so the editor can mark it."""

    try:
        lines = read_authored_text(skill_dir / "GRAPH.md").splitlines()
    except OSError:
        return None
    for index, line in enumerate(lines, start=1):
        if line.startswith("name:"):
            return index
    return None


def _lint_error_from_compile_error(error: CompileError) -> LintError:
    return LintError(
        file=error.file,
        line=error.line,
        column=None,
        error_code=error.error_code or "STUDIO_COMPILE_PREFLIGHT_FAILED",
        severity="warning" if error.severity == "warning" else "error",
        message=error.message,
        phase_name=None,
        field_path=error.field,
        source_path=error.file,
    )


def _configured_role_names() -> set[str]:
    """Role names configured in the global llm_roles.yaml (empty if absent/unreadable)."""
    from app.services.llm_roles import load_roles_file, roles_path

    path = roles_path()
    if not path.exists():
        return set()
    try:
        data = load_roles_file(path)
    except Exception:  # noqa: BLE001 - a malformed roles file must never break linting
        return set()
    return set(data.roles.keys())


def _frontmatter_llm_role_value(frontmatter: dict[str, Any]) -> str | None:
    value = frontmatter.get("llm_role")
    if not isinstance(value, str):
        return None
    value = value.strip().strip('"').strip("'").strip()
    return value or None


# LLM role warnings are now handled directly by the engine compiler via allowed_roles.


def lint_skill_changed_markdown(
    skill_id: str,
    markdown: str,
    *,
    file_path: str | None = None,
    workspace_root: str | None = None,
) -> LintResult:
    """Lint the editor's *unsaved* markdown body for a skill file (no disk write).

    The lint kernel stays engine-owned (compile-lint F1/F5): we hand the changed
    markdown to the engine compiler and surface its diagnostics. Persistence is
    Autosave / native-fs's job, so the skill store on disk is never mutated. The
    engine compiler is path-based and also reads sibling files (phase docs,
    inline IO), so we materialize an *ephemeral* copy of the skill tree in the OS
    temp dir, overwrite only the actively edited file, compile that copy
    with caching off, and tear the copy down — nothing touches the skill store.
    """
    logger.info(
        "lint changed-markdown skill_id=%s file_path=%s bytes=%d",
        skill_id,
        file_path or "GRAPH.md",
        len(markdown),
    )
    overlay_path = _safe_lint_overlay_path(file_path)
    disk_dir = _resolve_skill_dir_for_lint(skill_id, workspace_root=workspace_root)
    with tempfile.TemporaryDirectory(prefix="studio-lint-") as tmp_root:
        sandbox = Path(tmp_root) / "skill"
        _materialize_lint_sandbox(disk_dir, markdown, sandbox, overlay_path)
        result = lint_skill_path(sandbox)
    logger.info("lint changed-markdown skill_id=%s status=%s", skill_id, result.status)
    return _relocate_lint_files_to_skill_root(result, sandbox)


def _resolve_skill_dir_for_lint(skill_id: str, *, workspace_root: str | None = None) -> Path | None:
    """Resolve the on-disk skill dir, tolerating a not-yet-saved skill.

    A brand-new skill the user is drafting may have no disk tree yet; linting its
    unsaved body must still work, so a missing skill resolves to ``None`` and the
    sandbox is built from the body alone.
    """
    if workspace_root:
        return _requested_workspace_root_or_none(skill_id, workspace_root)

    try:
        return resolve_skill_dir(skill_id)
    except HTTPException:
        logger.info("lint changed-markdown skill_id=%s has no disk tree; body-only sandbox", skill_id)
        return None


def _requested_workspace_root_or_none(skill_id: str, workspace_root: str) -> Path | None:
    """The requested workspace root if it is one of ours, else ``None`` to fall back.

    Two different answers to two different questions, which the previous single
    ``root.exists() and root.is_dir()`` check ran together:

    - **Is it ours?** A directory outside every workspace this Studio has open is
      REFUSED, not fallen back from. Falling back was the hole: any directory on
      the machine passed the existence test, so lint read (and, on the
      changed-markdown branch, copied into a sandbox) trees belonging to nobody.
      A refusal is also why the value no longer reaches ``logger`` — a string
      nobody had proved was a path became a line in a log people read as the
      record of what happened (CodeQL ``py/log-injection``).
    - **Is it there yet?** A root inside our boundary that does not exist is the
      brand-new-skill case the fallback exists for, and it keeps it.
    """
    try:
        root = resolve_within_roots(workspace_root, studio_workspace_roots())
    except PathEscapesDirectory:
        _raise_workspace_root_outside_boundary(skill_id, workspace_root)
    if root.is_dir():
        return root
    logger.info(
        "lint skill_id=%s requested workspace root is not on disk yet; falling back",
        skill_id,
    )
    return None


def _safe_lint_overlay_path(file_path: str | None) -> Path:
    raw_path = (file_path or "GRAPH.md").strip()
    if not raw_path:
        raw_path = "GRAPH.md"
    overlay_path = Path(raw_path.replace("\\", "/"))
    if overlay_path.is_absolute() or any(part in {"", ".", ".."} for part in overlay_path.parts):
        raise HTTPException(
            status_code=400,
            detail={"message": f"Invalid lint file path: {file_path}"},
        )
    return overlay_path


def _materialize_lint_sandbox(
    disk_dir: Path | None,
    markdown: str,
    sandbox: Path,
    overlay_path: Path,
) -> None:
    """Build an ephemeral compile sandbox: disk siblings + the changed file."""
    if disk_dir is not None and disk_dir.exists():
        shutil.copytree(disk_dir, sandbox)
    else:
        sandbox.mkdir(parents=True, exist_ok=True)
    target = sandbox / overlay_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")


def _relocate_lint_files_to_skill_root(result: LintResult, sandbox: Path) -> LintResult:
    """Strip the throwaway sandbox prefix from any absolute file in diagnostics.

    Diagnostics file paths are already skill-relative (e.g. ``GRAPH.md``); this
    only guards against an absolute sandbox path leaking into the response.
    """
    sandbox_str = str(sandbox)
    relocated = [
        error.model_copy(update={"file": _strip_sandbox_prefix(error.file, sandbox_str)})
        if error.file and error.file.startswith(sandbox_str)
        else error
        for error in result.errors
    ]
    if relocated == result.errors:
        return result
    return result.model_copy(update={"errors": relocated})


def _strip_sandbox_prefix(file_path: str, sandbox_str: str) -> str:
    return file_path[len(sandbox_str) :].lstrip("/\\")


async def compile_skill_for_studio(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> CompileSuccess:
    """Compile a resolved skill, broadcast the outcome, return the Studio contract.

    The broadcast lives here rather than in the HTTP route because this function is
    the only common downstream of the route and the MCP tool — the frontend must
    learn about a compile whoever started it (决议 2026-08-03 D2).

    A compile announces its start as well as its outcome, the way predict and run do.
    That opening event is what separates two consecutive occurrences: recompiling
    unchanged source settles on the identical outcome, and without something between
    them the receiver reads the second settle as a redelivery of the first and folds
    its side effects away (决议 2026-08-09 D4).
    """
    await publish_skill_gate(skill_id=skill_id, gate="compile", outcome="started")
    try:
        success = await _compile_skill_for_studio(user_id, skill_id, storage, metadata)
    except CompileFailedError as exc:
        await publish_skill_gate(
            skill_id=skill_id,
            gate="compile",
            outcome="fail",
            defect_count=len(exc.failure.errors),
            errors=[error.model_dump(mode="json") for error in exc.failure.errors],
        )
        raise
    except Exception:
        # Announcing a start obliges this gate to announce an end. A `started` with no
        # terminal parks every receiver on `compiling` with nothing left able to move
        # it (决议 2026-08-09 D1) — a crash is an end, so it is reported as one. The
        # exception itself still propagates; the caller decides what it means.
        await publish_skill_gate(skill_id=skill_id, gate="compile", outcome="fail")
        raise
    await publish_skill_gate(
        skill_id=skill_id,
        gate="compile",
        outcome="pass",
        content_hash=str(success.artifact_ref.get("content_hash") or "") or None,
    )
    return success


async def _compile_skill_for_studio(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> CompileSuccess:
    """Compile a resolved skill and return the Studio compile contract."""
    skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    runtime_config = refresh_runtime_config(skill_dir)
    try:
        compiled = compile_skill(
            skill_dir,
            cache=False,
            skill_resolver=build_studio_skill_resolver(),
            runtime_input_fields=runtime_input_fields_for_engine(runtime_config),
            allowed_roles=_configured_role_names(),
        )
    except (GraphCompileError, ResourceNotFoundError) as exc:
        failure = _compile_failure_from_exception(exc, skill_dir)
        preflight_errors = _runtime_input_preflight_errors_from_graph_frontmatter(
            skill_dir,
            runtime_config,
        )
        if preflight_errors:
            errors = [*failure.errors, *preflight_errors]
            count = len(errors)
            noun = "error" if count == 1 else "errors"
            failure = CompileFailure(
                detail=f"Skill compilation failed with {count} {noun}",
                errors=errors,
            )
        raise CompileFailedError(failure) from exc

    # Studio preflight gates own workspace files that engine compile intentionally does
    # not know about: runtime root inputs and golden outputs. Anything provably
    # invalid before running predict/run must fail compile.
    runtime_input_errors = _validate_runtime_inputs_against_graph_input_schema(compiled, runtime_config)

    # N4 atom #35: Studio-layer business gate. A persisted golden case whose node's
    # current io.outputs schema now requires fields the golden is missing (output-schema
    # drift) must FAIL compile so the existing N3 compile-gating blocks predict until the
    # golden is reconciled. Binds to the output schema only; the engine compile has no
    # knowledge of Studio golden files, so this gate lives in the shell, after compile.
    golden_errors = _validate_golden_against_output_schema(skill_id, str(skill_dir))
    preflight_errors = [*runtime_input_errors, *golden_errors]
    if preflight_errors:
        count = len(preflight_errors)
        noun = "error" if count == 1 else "errors"
        if runtime_input_errors and golden_errors:
            detail = f"Compile preflight found {count} runtime input/golden {noun}"
        elif runtime_input_errors:
            detail = f"Runtime input bindings do not match the graph input schema ({count} {noun})"
        else:
            detail = f"Golden baseline files do not match node output schemas ({count} {noun})"
        raise CompileFailedError(
            CompileFailure(
                detail=detail,
                errors=preflight_errors,
            )
        )

    artifact_ref = build_engine_adapter().compile(
        {
            "skill_dir": str(skill_dir),
            "skill_id": skill_id,
            "artifact_scope": "ephemeral",
            "runtime_config": runtime_config,
        }
    )
    lint_result = LintResult(
        status="passed",
        errors=[],
        phases_summary=_phase_summary_from_compiled(compiled),
    )
    detail = await _detail_from_manifest_async(
        user_id,
        skill_id,
        skill_dir,
        compiled,
        lint_result,
        storage,
        metadata,
    )
    return CompileSuccess(
        skill_id=skill_id,
        status="ok",
        phase_count=len(compiled.manifest.phases),
        manifest_name=compiled.manifest.name,
        artifact_ref=artifact_ref,
        source_map_ref=artifact_ref["source_map_ref"],
        execution_fingerprint=artifact_ref["execution_fingerprint"],
        detail=detail,
    )


def _validate_runtime_inputs_against_graph_input_schema(
    compiled: CompiledSkill,
    runtime_config: dict[str, Any],
) -> list[CompileError]:
    """Compile-time gate for Studio runtime root input bindings."""
    raw_inputs = _compiled_graph_input_schema(compiled)
    return _validate_runtime_inputs_against_raw_input_schema(raw_inputs, runtime_config)


def _runtime_input_preflight_errors_from_graph_frontmatter(
    skill_dir: Path,
    runtime_config: dict[str, Any],
) -> list[CompileError]:
    """Run Studio-owned runtime input checks even when engine compile stops early.

    Engine structure diagnostics and Studio runtime binding diagnostics are
    independent when GRAPH.md frontmatter is still parseable. Returning both in
    one compile/lint result keeps one broken field from masking another.
    """
    raw_inputs = _graph_input_schema_from_frontmatter(skill_dir)
    return _validate_runtime_inputs_against_raw_input_schema(raw_inputs, runtime_config)


def _validate_runtime_inputs_against_raw_input_schema(
    raw_inputs: dict[str, Any],
    runtime_config: dict[str, Any],
) -> list[CompileError]:
    if not raw_inputs:
        return []

    try:
        validator = Draft202012Validator(raw_inputs)
        validator.check_schema(raw_inputs)
    except SchemaError as exc:
        return [
            CompileError(
                file="GRAPH.md",
                field="io.inputs",
                severity="fatal",
                message=f"Graph input schema is invalid for runtime input validation: {exc.message}",
                error_code="STUDIO_RUNTIME_INPUT_SCHEMA_INVALID",
            )
        ]

    properties = raw_inputs.get("properties")
    if not isinstance(properties, dict):
        return []
    inputs = runtime_config.get("inputs")
    active = inputs.get("active") if isinstance(inputs, dict) else None
    root_bindings = active.get("root") if isinstance(active, dict) else None
    if not isinstance(root_bindings, dict):
        root_bindings = {}
    raw_conflicts = inputs.get("conflicts") if isinstance(inputs, dict) else None
    root_conflicts = raw_conflicts.get("root") if isinstance(raw_conflicts, dict) else None
    if not isinstance(root_conflicts, list):
        root_conflicts = []
    conflicts_by_field = {
        conflict.get("field"): conflict
        for conflict in root_conflicts
        if isinstance(conflict, dict) and isinstance(conflict.get("field"), str)
    }

    errors: list[CompileError] = []
    raw_required = raw_inputs.get("required")
    required = [field for field in raw_required if isinstance(field, str)] if isinstance(raw_required, list) else []
    for field in required:
        if field in conflicts_by_field:
            errors.append(_conflict_runtime_input_error(field, conflicts_by_field[field], blocking=True))
        elif field not in root_bindings:
            errors.append(_missing_runtime_input_error(field))

    # A conflict silently drops the binding (runtime_config only records the
    # clash, see runtime_config._bindings_from_entries), so a DECLARED optional
    # field loses its source with nothing else to show for it. Design
    # 03_regions/input/mvp1-alignment.md:42 scopes conflicts to schema fields —
    # report every declared one, but only the required ones block.
    for field in properties:
        if not isinstance(field, str) or field in required:
            continue
        if field in conflicts_by_field:
            errors.append(_conflict_runtime_input_error(field, conflicts_by_field[field], blocking=False))

    for field, binding in root_bindings.items():
        if not isinstance(field, str) or not isinstance(binding, dict):
            continue
        schema = properties.get(field)
        if not isinstance(schema, dict):
            continue
        actual_type = binding.get("type")
        if not isinstance(actual_type, str):
            continue
        if not _runtime_input_type_matches(schema.get("type"), actual_type):
            errors.append(
                CompileError(
                    file=".workspace/runtime_config.json",
                    field=field,
                    severity="fatal",
                    message=(
                        f"Runtime input field '{field}' has type '{actual_type}', "
                        f"but graph input schema expects {_format_expected_json_type(schema.get('type'))}."
                    ),
                    error_code="STUDIO_RUNTIME_INPUT_SCHEMA_INVALID",
                )
            )
    return errors


def _graph_input_schema_from_frontmatter(skill_dir: Path) -> dict[str, Any]:
    try:
        frontmatter, _body, _line_meta = parse_markdown_parts(skill_dir / "GRAPH.md")
    except Exception:  # noqa: BLE001 - engine parse diagnostics already own this failure.
        return {}
    io_block = frontmatter.get("io")
    if not isinstance(io_block, dict):
        return {}
    inputs = io_block.get("inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def _compiled_graph_input_schema(compiled: CompiledSkill) -> dict[str, Any]:
    raw = getattr(compiled, "raw", None)
    if not isinstance(raw, dict):
        return {}
    io_block = raw.get("io")
    if not isinstance(io_block, dict):
        return {}
    inputs = io_block.get("inputs")
    return dict(inputs) if isinstance(inputs, dict) else {}


def _missing_runtime_input_error(field: str) -> CompileError:
    return CompileError(
        file=".workspace/runtime_config.json",
        field=field,
        severity="fatal",
        message=(
            f"Graph input schema requires runtime input field '{field}', "
            "but runtime_config has no root import binding. Add a matching file under "
            ".workspace/import_files before predict/run."
        ),
        error_code="STUDIO_RUNTIME_INPUT_MISSING",
    )


def _conflict_runtime_input_error(
    field: str, conflict: dict[str, Any], *, blocking: bool
) -> CompileError:
    candidates = conflict.get("candidates")
    count = len(candidates) if isinstance(candidates, list) else 0
    consequence = (
        "This field is required, so predict/run cannot start until one remains."
        if blocking
        else "This optional field stays unbound until one remains."
    )
    return CompileError(
        file=".workspace/runtime_config.json",
        field=field,
        severity="fatal" if blocking else "warning",
        message=(
            f"Graph input schema field '{field}' has multiple runtime import candidates"
            f" ({count}). Keep only one matching field under .workspace/import_files "
            f"or rename the extra candidates. {consequence}"
        ),
        error_code="STUDIO_RUNTIME_INPUT_CONFLICT",
    )


def _runtime_input_type_matches(expected: object, actual: str) -> bool:
    if expected is None:
        return True
    if isinstance(expected, str):
        return actual == expected or (expected == "number" and actual == "integer")
    if isinstance(expected, list):
        return any(_runtime_input_type_matches(item, actual) for item in expected)
    return True


def _format_expected_json_type(expected: object) -> str:
    if isinstance(expected, str):
        return expected
    if isinstance(expected, list):
        return " or ".join(str(item) for item in expected)
    return "an unconstrained type"


def _validate_golden_against_output_schema(skill_id: str, skill_dir: str) -> list[CompileError]:
    """N4 #35: compile gate — golden cases must match current output schemas.

    For each agent node that has a persisted golden case, resolve the node's CURRENT
    ``io.outputs`` schema via the allowlisted engine port and validate the stored
    ``expected_output``. A stale golden = output-file drift that must block predict.
    Binds to the output schema only: prompt/agent-internal edits never appear in the
    schema so never trigger this.
    """
    # Deferred import avoids the golden_diff -> skills import cycle (golden_diff imports
    # resolve_skill_dir/golden_dir_for from this module).
    from app.services.golden_diff import iter_golden_cases_for_skill

    logger.info("golden_compile_gate action=start skill_id=%s", skill_id)
    adapter = build_engine_adapter()
    errors: list[CompileError] = []
    checked = 0
    for node_id, expected_output in iter_golden_cases_for_skill(Path(skill_dir)):
        output_schema = adapter.resolve_agent_node_output_schema(skill_dir, node_id)
        if output_schema is None:
            # Logic node (no golden semantics) or a golden whose node was removed —
            # not a schema-drift gap; the field-presence rule only applies to agent nodes.
            logger.info(
                "golden_compile_gate decision=skip skill_id=%s node_id=%s reason=no_agent_output_schema",
                skill_id,
                node_id,
            )
            continue
        checked += 1
        try:
            validator = Draft202012Validator(output_schema)
            validator.check_schema(output_schema)
        except SchemaError as exc:
            errors.append(
                CompileError(
                    field=f"{node_id}.io.outputs",
                    severity="fatal",
                    message=(
                        f"Output schema for agent node '{node_id}' is invalid for golden validation: {exc.message}"
                    ),
                    error_code="STUDIO_GOLDEN_SCHEMA_INVALID",
                )
            )
            continue
        for error in sorted(validator.iter_errors(expected_output), key=_jsonschema_error_sort_key):
            field = _jsonschema_error_field(error)
            golden_field = f"{node_id}.{field}" if field else node_id
            logger.warning(
                "golden_compile_gate decision=fail skill_id=%s node_id=%s field=%s reason=required_field_missing",
                skill_id,
                node_id,
                golden_field,
            )
            errors.append(
                CompileError(
                    severity="fatal",
                    field=golden_field,
                    message=(
                        f"Golden baseline for agent node '{node_id}' does not match "
                        f"current output schema: {error.message}. Reconcile the golden before predict."
                    ),
                    error_code="STUDIO_GOLDEN_SCHEMA_INVALID",
                )
            )
    logger.info(
        "golden_compile_gate action=end skill_id=%s checked_nodes=%d missing_fields=%d",
        skill_id,
        checked,
        len(errors),
    )
    return errors


def _jsonschema_error_sort_key(error: JsonSchemaValidationError) -> tuple[str, str]:
    return (".".join(str(part) for part in error.path), error.message)


def _jsonschema_error_field(error: JsonSchemaValidationError) -> str | None:
    path = ".".join(str(part) for part in error.path)
    if path:
        return path
    schema_path = list(error.schema_path)
    if "required" in schema_path and error.message.startswith("'"):
        return error.message.split("'", 2)[1]
    return None


def _skill_relative_posix(skill_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(skill_dir).as_posix()
    except ValueError:
        return path.as_posix()


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
    # No structure lint here: write_skill_files_atomic makes exactly that check
    # on exactly this directory its commit criterion, so reaching this line
    # already means the structure passed. What the detail still needs is the
    # full lint, Studio preflight included.
    write_skill_files_atomic(skill_dir, files)
    for rel_path in files:
        record_api_write(skill_dir.joinpath(*PurePosixPath(rel_path).parts))
    lint = lint_skill_path(skill_dir)
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
    current = read_authored_text(target) if target.exists() else ""
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
    """Unregister a skill from Studio without deleting its source directory."""
    _validate_skill_id_segment(skill_id)
    await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    await metadata.remove_skill_index_entry(skill_id)


def _is_safe_skill_id_segment(skill_id: str) -> bool:
    """Whether this id can name a directory at all, asked without raising.

    Same question as :func:`_validate_skill_id_segment`, for the callers whose
    answer to "no" is an empty result rather than a rejected request.
    """
    return bool(
        skill_id
        and Path(skill_id).name == skill_id
        and skill_id not in {".", ".."}
        and "/" not in skill_id
        and "\\" not in skill_id
        and _SAFE_SKILL_ID_RE.fullmatch(skill_id)
    )


def _validate_skill_id_segment(skill_id: str) -> str:
    segment = Path(skill_id).name
    if not _is_safe_skill_id_segment(skill_id):
        response = error_response(
            error_code="INVALID_SKILL_ID",
            http_status=400,
            message=f"Invalid skill id: {skill_id}",
            details={"skill_id": skill_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    return segment


def validate_run_id_segment(run_id: str) -> str:
    segment = Path(run_id).name
    if (
        not run_id
        or segment != run_id
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or not _SAFE_RUN_ID_RE.fullmatch(run_id)
    ):
        response = error_response(
            error_code="INVALID_RUN_ID",
            http_status=400,
            message=f"Invalid run id: {run_id}",
            details={"run_id": run_id},
            retry_strategy="not_retryable",
        )
        raise_error_response(response)
    return segment


def _raise_skill_not_found(skill_id: str) -> NoReturn:
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {skill_id}",
        {"skill_id": skill_id},
    )


async def create_new_skill(
    user_id: str,
    skill_id: str,
    files: dict[str, str],
    storage: StorageBackend,
    metadata: MetadataStore,
    directory_path: str | None = None,
    import_existing: bool = False,
) -> SkillSummary:
    """Create a new directory-based V2.1 skill."""
    index_entry = await metadata.get_skill_index_entry(skill_id)
    if index_entry is not None:
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    skill_dir = (
        await _validated_directory_path(user_id, skill_id, directory_path, metadata)
        if directory_path
        else await _default_skills_root(metadata) / skill_id
    )
    if import_existing:
        if not directory_path:
            _raise_invalid_directory_path("", "directory_path is required for import")
        if not skill_dir.exists() or not skill_dir.is_dir():
            _raise_invalid_directory_path(str(skill_dir), "selected folder does not exist")
        if not await _is_importable_skill_directory(skill_dir, storage):
            # WELCOME-2 / welcome F2 / 01_init.md D2 (FROZEN): "Open folder" must not
            # block on file shape. A folder lacking a Studio manifest (GRAPH.md/SKILL.md)
            # — empty or non-skill — imports into a repair state (compile/copilot
            # normalize it later) instead of being hard-rejected. Only OS-level guards
            # (path missing / not a directory, above) remain. The summary + detail paths
            # already degrade gracefully for a manifest-less folder.
            logger.warning(
                "import skill_id=%s dir=%s: no GRAPH.md/SKILL.md manifest; "
                "importing into repair state (D2: do not block on file shape)",
                skill_id,
                skill_dir,
            )
        elif await storage.exists(str(skill_dir / "GRAPH.md")):
            # Validate but do not raise on import, letting users upgrade/correct later.
            lint_skill_path(skill_dir)
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
        return summary

    if directory_path and await _directory_is_nonempty(skill_dir):
        _raise_invalid_directory_path(
            str(skill_dir),
            "Cannot create a new skill in a non-empty folder. Choose an empty folder or use Import skill.",
        )

    if await _is_importable_skill_directory(skill_dir, storage):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {skill_id}",
            {"skill_id": skill_id},
        )

    write_skill_files_atomic(skill_dir, files or _scaffold_files_for(skill_id))
    workspace_dir_for(skill_dir).mkdir(parents=True, exist_ok=True)
    initialize_skill_repository(skill_dir)
    try:
        summary = await _summary_for_skill_dir_async(
            user_id,
            skill_dir,
            storage,
            metadata,
            skill_id=skill_id,
        )
    except Exception:
        # 创建即校验失败(如非法种子 manifest)必须回滚刚写出的目录:失败的
        # create 不得留下半成品占住 skill_id,否则同名重试会被
        # _is_importable_skill_directory 误判为 SKILL_ALREADY_EXISTS。
        _rmtree_with_retry(skill_dir)
        raise
    summary = summary.model_copy(update={"directory_path": str(skill_dir)})
    await metadata.save_skill_index_entry(
        skill_id,
        {"absolute_path": str(skill_dir), "l2_remote_url": ""},
    )
    return summary


async def _default_skills_root(metadata: MetadataStore) -> Path:
    settings = await metadata.read_app_settings()
    if settings.default_skills_directory:
        return Path(settings.default_skills_directory).expanduser().resolve()
    return config.DEFAULT_SKILLS_ROOT


async def fork_skill(
    user_id: str,
    skill_id: str,
    new_skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillSummary:
    """Clone an existing skill into the default new-skill root under a new id."""
    if await metadata.get_skill_index_entry(new_skill_id) is not None:
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {new_skill_id}",
            {"skill_id": new_skill_id},
        )
    target_dir = await _default_skills_root(metadata) / new_skill_id
    target_path = target_dir / "GRAPH.md"
    if await storage.exists(str(target_path)):
        raise standard_http_exception(
            "SKILL_ALREADY_EXISTS",
            f"Skill already exists: {new_skill_id}",
            {"skill_id": new_skill_id},
        )

    source_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    await storage.copy_tree(str(source_dir), str(target_dir))
    try:
        # The copy is a file some outside editor may have signed. Reading it as
        # plain UTF-8 turns that signature into a leading character, and the write
        # below re-encodes it — handing the new skill a signature Studio itself
        # produced, which is what `CROSS_PLATFORM.md` forbids us to write.
        content = await storage.read_authored_text(str(target_path))
        await storage.write_text(
            str(target_path),
            _rewrite_forked_skill_content(content, old_id=skill_id, new_id=new_skill_id),
        )
        # Same structure-only gate as write_skill_files_atomic: a fork must not
        # fail because the source's role vanished from llm_roles.yaml since.
        lint = lint_skill_path(target_dir, include_studio_preflight=False, include_role_governance=False)
        if lint.status == "failed":
            _raise_manifest_validation_failed(lint)
        summary = await _summary_for_skill_dir_async(user_id, target_dir, storage, metadata)
        await metadata.save_skill_index_entry(
            new_skill_id,
            {"absolute_path": str(target_dir), "l2_remote_url": ""},
        )
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
    """Return the indexed writable skill body directory."""
    safe_skill_id = _validate_skill_id_segment(skill_id)
    indexed = await metadata.get_skill_index_entry(safe_skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if await _workspace_skill_body_exists(skill_dir, storage):
            return skill_dir

    del user_id
    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {safe_skill_id}",
        {"skill_id": safe_skill_id},
    )


async def resolve_skill_dir_async(
    user_id: str,
    skill_id: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> Path:
    """Resolve a skill id through the opened-skill absolute path index."""
    safe_skill_id = _validate_skill_id_segment(skill_id)
    indexed = await metadata.get_skill_index_entry(safe_skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if await storage.exists(str(skill_dir)):
            return skill_dir

    del user_id
    _raise_skill_not_found(safe_skill_id)


async def _resolve_canvas_serialize_dir(
    user_id: str,
    skill_id: str,
    workspace_root: str | None,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> Path:
    """Resolve the directory whose GRAPH.md a canvas topology-save targets.

    A drilled subgraph is identified by its ABSOLUTE PATH (MVP1 design: subgraph
    identity is a path, not a registry id). When the canvas passes that path as
    ``workspace_root`` we read/serialize THAT GRAPH.md directly, so a subgraph
    whose bare name collides with another skill (e.g. a top-level skill of the
    same name) is never mis-resolved through the global index / public dir.
    Without a path we fall back to bare-id resolution for the parent graph.

    The path is BOUNDED to the workspaces this Studio has open
    (:func:`studio_workspace_roots`). Absolute-plus-holds-a-GRAPH.md was not a
    bound: it is true of any directory on the machine that happens to hold one,
    and this endpoint hands the file's full text back to the caller in
    ``current_markdown_content`` whenever the optimistic-lock hash disagrees — so
    an unbounded root plus a deliberately wrong ``expected_hash`` read any
    GRAPH.md on disk.
    """
    if workspace_root:
        try:
            skill_dir = resolve_within_roots(workspace_root, studio_workspace_roots())
        except PathEscapesDirectory:
            _raise_workspace_root_outside_boundary(skill_id, workspace_root)
        if await storage.exists(str(skill_dir / "GRAPH.md")):
            return skill_dir
        _raise_skill_not_found(skill_id)
    return await resolve_skill_dir_async(user_id, skill_id, storage, metadata)


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
    """Return the indexed writable skill dir."""
    safe_skill_id = _validate_skill_id_segment(skill_id)
    indexed = _sync_skill_index_entry(safe_skill_id)
    if indexed:
        skill_dir = Path(indexed["absolute_path"])
        if _workspace_skill_body_exists_sync(skill_dir):
            return skill_dir

    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {safe_skill_id}",
        {"skill_id": safe_skill_id},
    )


# codeql[py/path-injection] skill_id is only joined into a path after _is_safe_skill_id_segment.
def opened_skill_dir(skill_id: str) -> Path | None:
    """The directory this Studio has open under that id, or None if it has none.

    The same lookup as :func:`resolve_skill_dir`, differing only in what "no"
    means to the caller. A request ABOUT a skill cannot proceed without its
    directory, so that one raises. A caller merely CONSULTING it — a resume
    asking which breakpoints stand on a skill it is not running from — needs the
    question to have an answer either way, or an absent skill turns into a
    failure of whatever it was consulted for.
    """
    if not _is_safe_skill_id_segment(skill_id):
        return None
    indexed = _sync_skill_index_entry(skill_id)
    if not indexed:
        return None
    skill_dir = Path(indexed["absolute_path"])
    return skill_dir if skill_dir.exists() else None


def resolve_skill_dir(skill_id: str) -> Path:
    """Resolve a skill id through the opened-skill absolute path index."""
    safe_skill_id = _validate_skill_id_segment(skill_id)
    skill_dir = opened_skill_dir(safe_skill_id)
    if skill_dir is not None:
        return skill_dir

    raise standard_http_exception(
        "SKILL_NOT_FOUND",
        f"Skill not found: {safe_skill_id}",
        {"skill_id": safe_skill_id},
    )


def run_dir_for(skill_id: str, run_id: str) -> Path:
    """Return the Studio V3 directory holding this run's artifacts.

    A predict lands in its own root (decision 2026-08-09 D13). The id is what
    says which, so every caller stays a two-argument call instead of carrying a
    kind it does not always know.
    """
    safe_run_id = validate_run_id_segment(run_id)
    return run_root_for(resolve_skill_dir(skill_id), safe_run_id) / safe_run_id


def workspace_dir_for(skill_dir: Path) -> Path:
    return skill_dir / ".workspace"


def runs_dir_for(skill_dir: Path) -> Path:
    return runs_root(workspace_dir_for(skill_dir))


def predicts_dir_for(skill_dir: Path) -> Path:
    return predicts_root(workspace_dir_for(skill_dir))


def run_root_for(skill_dir: Path, run_id: str) -> Path:
    """Which of the two roots this run's artifacts belong under."""
    return predicts_dir_for(skill_dir) if is_predict_run_id(run_id) else runs_dir_for(skill_dir)


def golden_dir_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "golden"


def local_settings_path_for(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "local_settings.json"


def test_inputs_dir_for_skill(skill_dir: Path) -> Path:
    return workspace_dir_for(skill_dir) / "import_files"


def skill_id_from_changed_path(path: Path) -> str | None:
    """Map a changed file path under watched roots back to a skill id."""
    resolved = path.resolve()
    roots = (config.DEFAULT_SKILLS_ROOT,)
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
        # One damaged record must not blank the skill list, which is why this
        # does not raise the way the run listing does — but it says which record
        # it could not read, because a "latest run" that silently skips runs is
        # indistinguishable from one that is simply older than you expect. The
        # catch names the two ways a record goes bad; anything else is a bug in
        # this function and belongs in the traceback.
        try:
            candidates.append(
                RunMetadata.model_validate_json(read_published_text(metadata_path)),
            )
        except (OSError, ValidationError) as exc:
            logger.warning("Skipping unreadable run record %s: %s", metadata_path, exc)
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
    if lint.status == "passed" or lint.phases_summary is not None:
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
    elif (lint := lint_skill_path(skill_dir)).status == "passed" or lint.phases_summary is not None:
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


async def _is_importable_skill_directory(path: Path, storage: StorageBackend) -> bool:
    return await storage.exists(str(path / "GRAPH.md")) or await storage.exists(str(path / "SKILL.md"))


# codeql[py/path-injection] callers provide paths assembled from validated skill ids or stored trusted skill metadata.
async def _workspace_skill_body_exists(path: Path, storage: StorageBackend) -> bool:
    if not await storage.exists(str(path)):
        return False
    child_names = await storage.list_dirs(str(path))
    files = await asyncio.to_thread(
        lambda: [child.name for child in path.iterdir() if child.is_file()] if path.exists() else [],
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
    return resolved_skill_dir


def _raise_invalid_directory_path(
    directory_path: str,
    message: str,
    *,
    required_entry: str | None = None,
) -> None:
    details = {"directory_path": directory_path}
    if required_entry:
        details["required_entry"] = required_entry
    response = error_response(
        error_code="INVALID_DIRECTORY_PATH",
        http_status=422,
        message=message,
        details=details,
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
        graph_topology=_graph_topology(compiled, skill_dir),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
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
        graph_topology=_graph_topology(compiled, skill_dir),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=latest,
        lint_result=lint_result,
        manifest_errors=[],
    )


def _graph_topology_projection_or_empty(
    skill_dir: Path,
) -> tuple[list[str], list[dict[str, object]]]:
    graph_path = skill_dir / "GRAPH.md"
    if not graph_path.exists():
        return [], []
    try:
        projection = load_graph_topology_projection(skill_dir)
    except (OSError, UnicodeDecodeError, GraphAgentError, ValueError) as exc:
        # The repair-state view depends on this graceful ([], []) degradation,
        # so Studio only logs visibility while Engine/core owns GRAPH parsing.
        logger.warning(
            "Failed to parse broken GRAPH.md at %s: %s: %s; degrading to empty topology/phases for repair view",
            graph_path,
            type(exc).__name__,
            exc,
        )
        return [], []
    return projection.phases, projection.graph_topology


def _current_graph_phase_count(skill_dir: Path) -> int:
    phases, _topology = _graph_topology_projection_or_empty(skill_dir)
    return len(phases)


async def _broken_detail_from_files_async(
    user_id: str,
    skill_id: str,
    skill_dir: Path,
    lint_result: LintResult,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> SkillDetail:
    latest = await latest_run_metadata_async(user_id, skill_id, metadata)
    phases, topology = _graph_topology_projection_or_empty(skill_dir)
    return SkillDetail(
        manifest=GraphManifest(
            schema_version="v0.3.0",
            name=skill_id,
            description="(broken: manifest invalid)",
            io={
                "inputs": {"type": "object", "properties": {}},
                "outputs": {"type": "object", "properties": {}},
            },
            phases=phases,
        ),
        graph_topology=topology,
        node_schema_v21=_node_schema_v21(),
        io_schema={},
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        # Broken/V1 details still expose the real asset tree for the Explorer panel.
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=latest,
        lint_result=lint_result,
        manifest_errors=lint_result.errors,
    )


async def _path_resolved_detail_from_files_async(
    skill_id: str,
    skill_dir: Path,
    lint_result: LintResult,
    storage: StorageBackend,
) -> SkillDetail:
    """Build a SkillDetail for a directory already resolved by path.

    Subgraph inline editing is path-owned: the parent skill's SUBGRAPH.md points
    at a concrete child directory that may not be registered in the global skill
    index. Resolving `/skills/{child_id}` would guess a different identity; this
    helper keeps the detail pinned to the already validated child path.
    """
    if lint_result.status == "failed" and lint_result.phases_summary is None:
        phases, topology = _graph_topology_projection_or_empty(skill_dir)
        return SkillDetail(
            manifest=GraphManifest(
                schema_version="v0.3.0",
                name=skill_id,
                description="(broken: manifest invalid)",
                io={
                    "inputs": {"type": "object", "properties": {}},
                    "outputs": {"type": "object", "properties": {}},
                },
                phases=phases,
            ),
            graph_topology=topology,
            node_schema_v21=_node_schema_v21(),
            io_schema={},
            file_paths={
                "skill_dir": str(skill_dir),
                "graph_md": str(skill_dir / "GRAPH.md"),
                "runs_dir": str(runs_dir_for(skill_dir)),
                "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
                "golden_dir": str(golden_dir_for(skill_dir)),
                "local_settings": str(local_settings_path_for(skill_dir)),
            },
            files=_read_skill_files(skill_dir),
            has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
            latest_run_metadata=None,
            lint_result=lint_result,
            manifest_errors=lint_result.errors,
        )

    compiled = _load_compiled(skill_dir)
    return SkillDetail(
        manifest=compiled.manifest,
        graph_topology=_graph_topology(compiled, skill_dir),
        node_schema_v21=_node_schema_v21(),
        io_schema=_io_schema(compiled),
        file_paths={
            "skill_dir": str(skill_dir),
            "graph_md": str(skill_dir / "GRAPH.md"),
            "runs_dir": str(runs_dir_for(skill_dir)),
            "test_inputs_dir": str(test_inputs_dir_for_skill(skill_dir)),
            "golden_dir": str(golden_dir_for(skill_dir)),
            "local_settings": str(local_settings_path_for(skill_dir)),
        },
        files=_read_skill_files(skill_dir),
        has_golden=await storage.exists(str(golden_dir_for(skill_dir))),
        latest_run_metadata=None,
        lint_result=lint_result,
        manifest_errors=[],
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
            files[rel_path] = read_authored_text(path)
        except UnicodeDecodeError:
            continue
    return files


def _read_current_graph_markdown(skill_dir: Path) -> str:
    graph_path = skill_dir / "GRAPH.md"
    if not graph_path.exists():
        return ""
    return read_authored_text(graph_path)


def studio_workspace_roots() -> list[Path]:
    """Every directory a caller-supplied ``workspace_root`` is allowed to be inside.

    A request may name the directory whose ``GRAPH.md`` it is editing — the canvas
    does it for a drilled subgraph, because MVP1 identifies a subgraph by PATH
    rather than by registry id (``_resolve_canvas_serialize_dir``). That value has
    to be bounded, and the honest bound is the set of places Studio is actually
    editing: the managed skills root, plus the absolute path of every skill this
    Studio has open.

    Not "the named skill's own tree", which is the tighter rule
    :func:`_allowed_child_graph_roots` states for a subgraph CHILD path. It
    cannot be used here: for a drilled child the frontend derives the skill id
    FROM the path (``workspace-identity.ts::skillIdFromWorkspaceRoot``), so that
    id need not be in the index at all, and requiring it to resolve would refuse
    exactly the legitimate drilled-child saves the field exists for. Nothing is
    lost by the wider set: to have drilled in, the user went through
    ``get_child_graph_topology``, which already enforced the tighter rule, so
    every reachable child path is inside an opened workspace anyway.
    """
    roots = [config.DEFAULT_SKILLS_ROOT]
    roots.extend(Path(entry["absolute_path"]) for entry in _sync_skill_index().values())
    return roots


def _raise_workspace_root_outside_boundary(skill_id: str, workspace_root: str) -> NoReturn:
    """Refuse a ``workspace_root`` that is not inside a workspace we have open.

    Reuses ``SUBGRAPH_PATH_INVALID`` because that is what the value IS — the
    absolute path of a drilled subgraph — and the frontend already renders that
    code as the red "this path does not resolve" state
    (``panels/PropertiesPanel.tsx``, ``subgraph-path.ts``).

    Echoes the value AS SENT rather than as resolved. The caller learns nothing
    from being told its own string back, whereas the resolved form would report
    where a symlink it named actually points — a fact about this machine that a
    refused request has no business returning.
    """
    _raise_subgraph_path_invalid(
        workspace_root,
        f"workspace_root is not inside a workspace Studio has open (skill {skill_id})",
    )


def _allowed_child_graph_roots(parent_skill_dir: Path) -> list[Path]:
    """Allowed roots a subgraph child path may resolve inside (copilot cwd boundary).

    Per engine skill-syntax §2.1, a subgraph child path must fall within the
    copilot working-directory boundary. In Studio that boundary is the managed
    skill roots: the parent skill's own tree plus the workspace and bundled
    skill roots.
    """
    roots = [
        parent_skill_dir,
        config.DEFAULT_SKILLS_ROOT,
    ]
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve(strict=False))
        except OSError:
            continue
    return resolved


def _raise_subgraph_path_invalid(child_path: str, reason: str) -> NoReturn:
    response = error_response(
        error_code="SUBGRAPH_PATH_INVALID",
        http_status=422,
        message=f"Invalid subgraph child path: {reason}",
        details={"path": child_path, "reason": reason},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


def _raise_subgraph_path_not_found(child_path: str) -> NoReturn:
    response = error_response(
        error_code="SUBGRAPH_PATH_NOT_FOUND",
        http_status=404,
        message=f"Subgraph child graph not found at path: {child_path}",
        details={"path": child_path},
        retry_strategy="not_retryable",
    )
    raise_error_response(response)


async def get_child_graph_topology(
    user_id: str,
    skill_id: str,
    child_path: str,
    storage: StorageBackend,
    metadata: MetadataStore,
) -> ChildGraphTopology:
    parent_skill_dir = await resolve_skill_dir_async(user_id, skill_id, storage, metadata)
    try:
        projection = load_child_graph_topology_projection(
            parent_skill_dir=parent_skill_dir,
            child_path=child_path,
            allowed_roots=_allowed_child_graph_roots(parent_skill_dir),
        )
    except SubgraphTopologyProjectionError as exc:
        if exc.code == "SUBGRAPH_PATH_NOT_FOUND":
            _raise_subgraph_path_not_found(child_path)
        _raise_subgraph_path_invalid(child_path, exc.reason)
    child_dir = Path(projection.path)
    detail = await _path_resolved_detail_from_files_async(
        projection.name or child_dir.name,
        child_dir,
        lint_skill_path(child_dir),
        storage,
    )
    return ChildGraphTopology(
        path=projection.path,
        name=projection.name,
        description=projection.description,
        phases=projection.phases,
        graph_topology=projection.graph_topology,
        detail=detail,
    )


def _graph_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_compiled(skill_path: Path) -> CompiledSkill:
    runtime_config = refresh_runtime_config(skill_path)
    try:
        return SkillLoader().compile_skill(
            skill_path,
            skill_resolver=build_studio_skill_resolver(),
            runtime_input_fields=runtime_input_fields_for_engine(runtime_config),
        )
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
    skill_dir = await _resolve_canvas_serialize_dir(user_id, skill_id, request.workspace_root, storage, metadata)
    graph_path = skill_dir / "GRAPH.md"
    # `read_authored_text`, not `read_text`: this value is hashed against a hash
    # the CALLER computed from text read by a reader that drops the signature
    # (`native_fs.rs`). The lock only holds if both sides decode the file the same
    # way.
    original_md = await storage.read_authored_text(str(graph_path))
    current_hash = _graph_content_hash(original_md)
    try:
        if request.expected_hash is not None and request.expected_hash != current_hash:
            raise CanvasConflictError(
                current_hash=current_hash,
                current_markdown_content=original_md,
                current_phase_count=_current_graph_phase_count(skill_dir),
            )
        # Build the canvas's desired topology (id + real depends_on) and serialize it.
        # NOTE: GraphManifest.phases is list[str] (no edges), so we MUST pass the full
        # phase refs to the topology serializer — cramming GraphPhaseRef into the
        # manifest's phases and re-validating raises ValidationError (the first half of
        # the bug that 500'd every canvas topology save and left orphan phase dirs).
        refs = [
            GraphPhaseRef(
                id=phase.id,
                src=phase.src,
                depends_on=list(phase.depends_on),
                output=phase.output,
            )
            for phase in request.phases
        ]
        markdown = serialize_graph_topology_from_markdown(
            skill_id=skill_id,
            original_md=original_md,
            phases=refs,
        )
    except CanvasConflictError:
        raise
    except CanvasSerializerFatal as exc:
        exc.elapsed_ms = (time.perf_counter() - started) * 1000
        raise
    except GraphTopologySerializationError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise CanvasSerializerFatal(
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            elapsed_ms=elapsed_ms,
        ) from exc
    except GraphAgentError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        raise _serializer_fatal_from_engine_error(exc, elapsed_ms) from exc
    elapsed_ms = (time.perf_counter() - started) * 1000
    return SerializeGraphRes(
        markdown_content=markdown,
        phase_count=len(request.phases),
        elapsed_ms=elapsed_ms,
        current_hash=current_hash,
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
            "name": phase_name,
            "tier": mode_by_phase.get(phase_name, ""),
            "has_validator": False,
        }
        for phase_name in compiled.manifest.phases
    ]


def _graph_topology(compiled: CompiledSkill, skill_dir: Path) -> list[dict[str, object]]:
    mode_by_phase = {node.phase_name: node.mode for node in compiled.nodes}
    # n2-canvas#10: precompute the per-phase io field schema + graph-level input
    # fields ONCE so each row can carry its own io fields and a supply/demand map
    # for the Canvas data-gap view (read-only projection over compiled.nodes).
    phase_io_index = build_phase_io_index(compiled)
    graph_input_fields = _graph_input_field_names(compiled)
    runtime_input_fields = runtime_input_fields_for_engine(refresh_runtime_config(skill_dir))
    topology = compiled.raw.get("graph_topology", {})
    rows = topology.get("phases", []) if isinstance(topology, dict) else []
    if isinstance(rows, list):
        return [
            _topology_row(
                name,
                list(depends_on),
                mode_by_phase.get(name, ""),
                skill_dir,
                phase_io_index=phase_io_index,
                graph_input_fields=graph_input_fields,
                runtime_input_fields=runtime_input_fields,
                output=row.get("output") is True,
            )
            for row in rows
            if isinstance(row, dict)
            and isinstance((name := row.get("name")), str)
            and isinstance((depends_on := row.get("depends_on")), list)
        ]
    return [
        _topology_row(
            phase_name,
            [],
            mode_by_phase.get(phase_name, ""),
            skill_dir,
            phase_io_index=phase_io_index,
            graph_input_fields=graph_input_fields,
            runtime_input_fields=runtime_input_fields,
        )
        for phase_name in compiled.manifest.phases
    ]


def _graph_input_field_names(compiled: CompiledSkill) -> set[str]:
    """Graph-level ``io.inputs`` field names (delegated to the data-gap projector)."""
    from app.services.canvas_data_gap import _graph_input_fields

    return _graph_input_fields(compiled)


def _topology_row(
    phase_name: str,
    depends_on: list[str],
    mode: str,
    skill_dir: Path,
    *,
    phase_io_index: dict[str, dict[str, dict[str, object]]] | None = None,
    graph_input_fields: set[str] | None = None,
    runtime_input_fields: dict[str, set[str]] | None = None,
    output: bool = False,
) -> dict[str, object]:
    """Build one topology row.

    Surfaces a subgraph phase's absolute child path AND (n2-canvas#10) the
    phase's per-node io field schema plus a supply/demand map: for each input
    field, which upstream phase or graph input supplies it, or whether it is a
    data gap. All source data comes from the already-compiled graph.
    """
    row: dict[str, object] = {
        "id": phase_name,
        "src": f"phases/{phase_name}",
        "depends_on": depends_on,
        "mode": mode,
    }
    if mode == "subgraph":
        row["path"] = read_subgraph_path(skill_dir, phase_name)
    if output:
        row["output"] = True
    if phase_io_index is not None:
        io_fields = phase_io_index.get(phase_name, {"inputs": {}, "outputs": {}})
        row["io_fields"] = io_fields
        row["field_supply"] = compute_field_supply(
            phase_name=phase_name,
            depends_on=depends_on,
            phase_io_index=phase_io_index,
            graph_input_fields=graph_input_fields or set(),
            runtime_input_fields=runtime_input_fields,
        )
    return row


def _node_schema_v21() -> dict[str, dict[str, object]]:
    return {
        "graph_phase_ref": GraphPhaseRef.model_json_schema(),
        "agent": AgentNodeAST.model_json_schema(),
        "logic": LogicNodeAST.model_json_schema(),
        "subgraph": SubgraphNodeAST.model_json_schema(),
    }


def _io_schema(compiled: CompiledSkill) -> dict[str, dict[str, object]]:
    return {
        "inputs": dict(compiled.raw["io"]["inputs"]),
        "outputs": dict(compiled.raw["io"]["outputs"]),
    }


def _has_golden(skill_dir: Path) -> bool:
    return golden_dir_for(skill_dir).exists()


def _sync_skill_index() -> dict[str, dict[str, str]]:
    index_path = config.SKILL_INDEX_PATH
    if not index_path.exists():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    index: dict[str, dict[str, str]] = {}
    for skill_id, entry in raw.items():
        if not isinstance(skill_id, str) or not isinstance(entry, dict):
            continue
        if not isinstance(entry.get("absolute_path"), str):
            continue
        remote_url = entry.get("l2_remote_url")
        index[skill_id] = {
            "absolute_path": entry["absolute_path"],
            "l2_remote_url": remote_url if isinstance(remote_url, str) else "",
        }
    return index


def _sync_skill_index_entry(skill_id: str) -> dict[str, str] | None:
    return _sync_skill_index().get(skill_id)


def registered_skill_id_for_dir(skill_dir: Path) -> str | None:
    """The skill id whose index entry points at this directory, if any.

    The reverse of :func:`resolve_skill_dir`. Ported from the Rust writer's
    ``registered_skill_id_for_root`` (``apps/studio/tauri/src/native_fs.rs``) —
    the index is the registry that answers "what is this folder called here",
    and asking it beats trusting whatever the folder's own manifest claims.
    """

    wanted = _index_path_key(skill_dir)
    for skill_id, entry in _sync_skill_index().items():
        if _index_path_key(Path(entry["absolute_path"])) == wanted:
            return skill_id
    return None


def _index_path_key(path: Path) -> str:
    # normcase folds Windows case + separators so D:\x and d:/x are one folder;
    # on POSIX it is the identity, keeping case significant where it must be.
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))


def _lint_errors_from_exception(exc: Exception, skill_dir: Path | None = None) -> list[LintError]:
    """Expand the engine's aggregated ``compile_result.issues`` into LintErrors.

    Falls back to the single primary exception when no aggregated issues ride
    on the seam (e.g. ``ResourceNotFoundError``).
    """
    compile_result = getattr(exc, "compile_result", None)
    issues = getattr(compile_result, "issues", None)
    if isinstance(issues, list) and issues:
        return [_lint_error_from_issue(issue, skill_dir) for issue in issues]
    return [_lint_error_from_exception(exc, skill_dir)]


def _lint_error_from_issue(issue: object, skill_dir: Path | None) -> LintError:
    """Map one engine CompileIssue (explicit axes) onto the Studio LintError."""
    severity = str(getattr(issue, "severity", "FATAL")).lower()
    message = str(getattr(issue, "message", "Skill compilation failed"))
    line = getattr(issue, "line", None)
    field_path = getattr(issue, "field_path", None)
    source_path = getattr(issue, "source_path", None)
    if not isinstance(source_path, str) or not source_path:
        source_path = None
    else:
        source_path = source_path.replace("\\", "/")
    return LintError(
        file=_lint_file_from_payload(issue, skill_dir),
        line=line if isinstance(line, int) else None,
        column=None,
        error_code=(_normalize_error_code(getattr(issue, "rule_id", None)) or _error_code_from_message(message)),
        severity="warning" if severity == "warning" else "error",
        message=message,
        phase_name=None,
        field_path=field_path if isinstance(field_path, str) else None,
        source_path=source_path,
    )


def _lint_error_from_exception(exc: Exception, skill_dir: Path | None = None) -> LintError:
    message = str(exc)
    match = _LOCATION_RE.search(message)
    line = int(match.group("line")) if match else None
    payload = getattr(exc, "payload", None)
    # Forward the engine's typed nearest-field locator verbatim (same getattr
    # pattern the manual Compile path uses for CompileError.field). The engine's
    # GraphAgentError surfaces payload.field_path/source_path onto the exception;
    # ``None`` here means the engine attributed no field → field-level Properties
    # projection degrades to the node/file axis (file/phase_name) downstream.
    field_path = _lint_str_attr(exc, "field_path")
    source_path = _lint_str_attr(exc, "source_path")
    return LintError(
        file=(_file_from_error_message(message, skill_dir) or _lint_file_from_payload(payload, skill_dir)),
        line=line,
        column=None,
        error_code=_lint_code_from_payload(payload) or _error_code_from_message(message),
        severity="error",
        message=message,
        phase_name=(_lint_phase_from_payload(payload) or _phase_from_location(match.group("loc") if match else None)),
        field_path=field_path,
        source_path=source_path,
    )


def _lint_str_attr(exc: Exception, name: str) -> str | None:
    """Read a non-empty str attribute off the engine exception, else ``None``."""
    value = getattr(exc, name, None)
    if not isinstance(value, str) or not value:
        return None
    if name == "source_path":
        return value.replace("\\", "/")
    return value


def _lint_code_from_payload(payload: object) -> str | None:
    """Prefer the engine's typed error code over regex-scraping the message."""
    code = getattr(payload, "code", None)
    if not isinstance(code, str) or not code:
        return None
    return code.strip("[]") or None


def _lint_file_from_payload(payload: object, skill_dir: Path | None = None) -> str | None:
    """Surface the engine's typed ``source_path`` as a skill-relative file."""
    source_path = getattr(payload, "source_path", None)
    if not isinstance(source_path, str) or not source_path:
        return None
    source_path = source_path.replace("\\", "/")
    relative = _relative_compile_path(source_path, skill_dir) if skill_dir is not None else None
    if relative and "/" in relative:
        return relative
    for candidate in ("GRAPH.md", "io/inputs.json", "io/outputs.json"):
        if source_path.endswith(candidate):
            return candidate
    phase_match = re.search(r"(phases/[A-Za-z0-9_-]+/(?:LOGIC|SUBGRAPH|SKILL)\.md)", source_path)
    if phase_match:
        return phase_match.group(1)
    return Path(source_path).name


def _lint_phase_from_payload(payload: object) -> str | None:
    phase_id = getattr(payload, "phase_id", None)
    if isinstance(phase_id, str) and phase_id:
        return phase_id
    return None


def _file_from_error_message(message: str, skill_dir: Path | None = None) -> str | None:
    location_file = _location_file_from_error_message(message, skill_dir)
    if location_file:
        return location_file
    for candidate in ("GRAPH.md", "io/inputs.json", "io/outputs.json"):
        if candidate in message:
            return candidate
    phase_match = re.search(r"(phases/[A-Za-z0-9_-]+/(?:LOGIC|SUBGRAPH|SKILL)\.md)", message)
    return phase_match.group(1) if phase_match else None


def _location_file_from_error_message(message: str, skill_dir: Path | None) -> str | None:
    pattern = re.compile(r"(?P<path>(?:[A-Za-z]:[\\/]|/)[^\n]*?(?:GRAPH|LOGIC|SUBGRAPH|SKILL)\.md):(?P<line>\d+)")
    match = pattern.search(message)
    if match is None:
        return None
    path = match.group("path")
    if skill_dir is not None:
        relative = _relative_compile_path(path, skill_dir)
        if relative:
            return relative
    normalized = path.replace("\\", "/")
    subgraph_index = normalized.find("subgraph/")
    if subgraph_index >= 0:
        return normalized[subgraph_index:]
    phases_index = normalized.find("phases/")
    if phases_index >= 0:
        return normalized[phases_index:]
    return Path(path).name


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
    # CompileIssue carries explicit skill-relative source_path/line/field_path
    # axes; no location-string parsing.
    source_path = getattr(issue, "source_path", None)
    file_path = _relative_compile_path(source_path, skill_dir) if isinstance(source_path, str) else None
    line = getattr(issue, "line", None)
    field = getattr(issue, "field_path", None)
    conflicting_phase = getattr(issue, "conflicting_phase", None)
    severity = str(getattr(issue, "severity", "fatal")).lower()
    return CompileError(
        file=file_path,
        line=line if isinstance(line, int) else None,
        field=field if isinstance(field, str) else None,
        severity="warning" if severity == "warning" else "fatal",
        message=str(getattr(issue, "message", "Skill compilation failed")),
        error_code=_normalize_error_code(getattr(issue, "rule_id", None)),
        conflicting_phase=conflicting_phase if isinstance(conflicting_phase, str) else None,
    )


def _compile_error_from_exception(exc: Exception, skill_dir: Path) -> CompileError:
    message = str(exc)
    match = _LOCATION_RE.search(message)
    line = getattr(exc, "line", None)
    if line is None and match:
        line = int(match.group("line"))
    file_path = _file_from_error_message(message, skill_dir) or _relative_compile_path(
        getattr(exc, "skill_path", None), skill_dir
    )
    return CompileError(
        file=file_path,
        line=line,
        field=getattr(exc, "field_path", None),
        severity="fatal",
        message=message,
        error_code=_compile_error_code_from_exception(exc),
    )


def _normalize_error_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip().strip("[]") or None


def _compile_error_code_from_exception(exc: Exception) -> str | None:
    payload = getattr(exc, "payload", None)
    code = _normalize_error_code(getattr(payload, "code", None))
    if code:
        return code
    error_payload = getattr(exc, "error_payload", None)
    if isinstance(error_payload, dict):
        code = _normalize_error_code(error_payload.get("code"))
        if code:
            return code
    return _normalize_error_code(_error_code_from_message(str(exc)))


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
        message=("V2.1 skills are directory-based; single-file SKILL.md authoring is not supported by this endpoint"),
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


def _rewrite_forked_skill_content(content: str, *, old_id: str, new_id: str) -> str:
    """Update frontmatter identity fields that exactly match the source id."""
    return "".join(
        _rewrite_identity_line(line, old_id=old_id, new_id=new_id) for line in content.splitlines(keepends=True)
    )


def _rewrite_identity_line(line: str, *, old_id: str, new_id: str) -> str:
    ending = ""
    body = line
    for candidate in ("\r\n", "\n", "\r"):
        if line.endswith(candidate):
            ending = candidate
            body = line.removesuffix(candidate)
            break

    for key in ("id", "name"):
        prefix = f"{key}:"
        if not body.startswith(prefix):
            continue
        raw_value = body[len(prefix) :]
        leading_space = raw_value[: len(raw_value) - len(raw_value.lstrip())]
        stripped = raw_value.strip()
        quote = stripped[0] if len(stripped) >= 2 and stripped[0] in {"'", '"'} and stripped[-1] == stripped[0] else ""
        value = stripped[1:-1] if quote else stripped
        if value != old_id:
            return line
        return f"{prefix}{leading_space}{quote}{new_id}{quote}{ending}"
    return line


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.rglob("*"):
        target_path = target / source_path.relative_to(source)
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(source_path.read_bytes())
