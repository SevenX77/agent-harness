"""read_file builtin tool for references-based progressive disclosure.

Wired to LLMPhase.references / AgentProfile.references. When a manifest
declares reference files, PhaseExecutor auto-mounts this tool so the LLM
can read them on demand instead of forcing large knowledge files into the
prompt.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from graph_agent.core.authored_text import read_authored_text

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE_BYTES = 200_000


class RuntimeInputFileError(ValueError):
    """Stable runtime error for declarative workspace file inputs."""


def _clean_path(path: str) -> str:
    cleaned = str(path or "").strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


def make_read_file_tool(
    allowed_paths: list[str],
    base_dir: Path,
) -> Callable[[dict[str, Any], str], str]:
    """Create a ``read_file`` callable bound to a skill directory.

    The returned tool allows reading explicitly declared reference files
    and files under ``base_dir/references``. All resolved paths must stay
    under ``base_dir`` and files over 200KB are rejected.
    """
    base_resolved = base_dir.resolve()
    references_root = (base_resolved / "references").resolve()

    allowed_resolved = _allowed_reference_paths(allowed_paths, base_resolved, references_root)

    def read_file(ctx: dict[str, Any], path: str) -> str:
        """Read a reference file's contents."""
        return _read_file_impl(
            ctx,
            path,
            base_resolved=base_resolved,
            references_root=references_root,
            allowed_resolved=allowed_resolved,
            allowed_paths=allowed_paths,
        )

    read_file.__name__ = "read_file"
    read_file.__doc__ = (
        "Read a reference file's contents from the skill's references/ directory.\n"
        "\n"
        f"Allowed reference files: {allowed_paths}\n"
        "\n"
        "Args:\n"
        "    path: relative path to the reference file "
        "(e.g. 'references/01_role.md' or '01_role.md')"
    )
    return read_file


def read_workspace_text_file(path: str, workspace_dir: Path) -> str:
    """Read a declared runtime input file from ``workspace_dir`` as UTF-8 text."""
    raw_path = str(path or "").strip().replace("\\", "/")
    if not raw_path:
        raise RuntimeInputFileError("file input path is empty")
    if Path(raw_path).is_absolute():
        raise RuntimeInputFileError(
            f"file input path {raw_path!r} escapes workspace_dir: absolute paths are not allowed"
        )

    workspace_root = Path(workspace_dir).resolve()
    target = _resolve_workspace_text_target(raw_path, workspace_root)
    return _read_utf8_text_target(target, raw_path)


def _resolve_workspace_text_target(raw_path: str, workspace_root: Path) -> Path:
    candidate = (workspace_root / raw_path).resolve(strict=False)
    _ensure_under_workspace(candidate, workspace_root, raw_path)

    if not candidate.exists():
        raise RuntimeInputFileError(f"file input {raw_path!r} not found")

    target = candidate.resolve()
    _ensure_under_workspace(target, workspace_root, raw_path)
    if target.is_dir():
        raise RuntimeInputFileError(f"file input {raw_path!r} is a directory")
    if not target.is_file():
        raise RuntimeInputFileError(f"file input {raw_path!r} is not a file")
    return target


def _ensure_under_workspace(candidate: Path, workspace_root: Path, raw_path: str) -> None:
    try:
        candidate.relative_to(workspace_root)
    except ValueError as exc:
        raise RuntimeInputFileError(
            f"file input path {raw_path!r} escapes workspace_dir"
        ) from exc


def _read_utf8_text_target(target: Path, raw_path: str) -> str:
    try:
        file_size = target.stat().st_size
    except OSError as exc:
        raise RuntimeInputFileError(f"file input {raw_path!r} could not be stat'ed") from exc
    if file_size > _MAX_FILE_SIZE_BYTES:
        raise RuntimeInputFileError(
            f"file input {raw_path!r} is too large "
            f"({file_size} bytes > {_MAX_FILE_SIZE_BYTES})"
        )

    try:
        data = target.read_bytes()
    except OSError as exc:
        raise RuntimeInputFileError(f"file input {raw_path!r} could not be read") from exc
    try:
        # utf-8-sig, not utf-8: the leading byte-order mark a Windows editor
        # writes is encoding, not the first character of the user's data.
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeInputFileError(
            f"file input {raw_path!r} is binary or non-text"
        ) from exc
    if "\x00" in text:
        raise RuntimeInputFileError(f"file input {raw_path!r} is binary or non-text")
    return text


def _allowed_reference_paths(
    allowed_paths: list[str],
    base_resolved: Path,
    references_root: Path,
) -> set[Path]:
    allowed_resolved: set[Path] = set()
    for raw_path in allowed_paths:
        path_clean = _clean_path(raw_path)
        if not path_clean:
            continue
        allowed_resolved.add((base_resolved / path_clean).resolve())
        allowed_resolved.add((references_root / path_clean).resolve())
    return allowed_resolved


def _read_file_impl(
    ctx: dict[str, Any],
    path: str,
    *,
    base_resolved: Path,
    references_root: Path,
    allowed_resolved: set[Path],
    allowed_paths: list[str],
) -> str:
    del ctx
    try:
        target = _find_read_file_target(path, base_resolved, references_root)
        if target is None:
            return (
                f"[read_file Error] File not found: {path!r}. "
                f"Available references: {allowed_paths}"
            )
        error = _validate_read_file_target(
            target,
            path,
            base_resolved=base_resolved,
            references_root=references_root,
            allowed_resolved=allowed_resolved,
            allowed_paths=allowed_paths,
        )
        if error is not None:
            return error
        file_size = target.stat().st_size
        content = read_authored_text(target)
        logger.info("read_file: %s (%d bytes)", target, file_size)
        return content
    except Exception as exc:  # noqa: BLE001
        return f"[read_file Error] {type(exc).__name__}: {exc}"


def _find_read_file_target(path: str, base_resolved: Path, references_root: Path) -> Path | None:
    path_clean = _clean_path(path)
    candidate_paths = [
        (base_resolved / path_clean).resolve(),
        (references_root / path_clean).resolve(),
    ]
    for candidate in candidate_paths:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _validate_read_file_target(
    target: Path,
    path: str,
    *,
    base_resolved: Path,
    references_root: Path,
    allowed_resolved: set[Path],
    allowed_paths: list[str],
) -> str | None:
    try:
        target.relative_to(base_resolved)
    except ValueError:
        return f"[read_file Error] Path escapes skill base_dir: {path!r}"

    if not _is_allowed_reference(target, allowed_resolved, references_root):
        return (
            f"[read_file Error] Path is not an allowed reference: {path!r}. "
            f"Available references: {allowed_paths}"
        )

    file_size = target.stat().st_size
    if file_size > _MAX_FILE_SIZE_BYTES:
        return (
            f"[read_file Error] File too large "
            f"({file_size} bytes > {_MAX_FILE_SIZE_BYTES}): {path!r}"
        )
    return None


def _is_allowed_reference(
    target: Path,
    allowed_resolved: set[Path],
    references_root: Path,
) -> bool:
    if target in allowed_resolved:
        return True
    try:
        target.relative_to(references_root)
        return True
    except ValueError:
        return False


def list_workspace_batch_files(
    dir_path: str, pattern: str, workspace_dir: Path
) -> list[tuple[int, Path]]:
    """List numbered batch files under a workspace-contained directory.

    ``pattern`` uses ``{n}`` as the number placeholder and ``*`` as a plain
    wildcard (e.g. ``chapter_{n}_latest_*.json``). Returns ``(number, path)``
    pairs sorted by the extracted number. Same containment rules as
    :func:`read_workspace_text_file`: no absolute paths, no workspace escape.
    """
    raw_dir = str(dir_path or "").strip().replace("\\", "/")
    if not raw_dir:
        raise RuntimeInputFileError("batch file input dir is empty")
    if Path(raw_dir).is_absolute():
        raise RuntimeInputFileError(
            f"batch file input dir {raw_dir!r} escapes workspace_dir: "
            "absolute paths are not allowed"
        )
    if "{n}" not in pattern:
        raise RuntimeInputFileError(
            f"batch file input pattern {pattern!r} has no {{n}} number placeholder"
        )

    workspace_root = Path(workspace_dir).resolve()
    target_dir = (workspace_root / raw_dir).resolve(strict=False)
    _ensure_under_workspace(target_dir, workspace_root, raw_dir)
    if not target_dir.is_dir():
        raise RuntimeInputFileError(f"batch file input dir {raw_dir!r} is not a directory")

    regex = re.compile(
        "^"
        + re.escape(pattern).replace(r"\{n\}", r"(\d+)").replace(r"\*", ".*")
        + "$"
    )
    matches: list[tuple[int, Path]] = []
    for entry in target_dir.iterdir():
        if not entry.is_file():
            continue
        match = regex.match(entry.name)
        if match is None:
            continue
        matches.append((int(match.group(1)), entry))
    if not matches:
        raise RuntimeInputFileError(
            f"batch file input {raw_dir!r} has no files matching {pattern!r}"
        )
    matches.sort(key=lambda item: item[0])
    return matches


def read_batch_file_text(target: Path, workspace_dir: Path) -> str:
    """Read one batch member (already containment-checked by listing)."""
    return _read_utf8_text_target(target, str(target))


__all__ = [
    "RuntimeInputFileError",
    "list_workspace_batch_files",
    "make_read_file_tool",
    "read_batch_file_text",
    "read_workspace_text_file",
]
