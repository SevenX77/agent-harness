"""read_file builtin tool for references-based progressive disclosure.

Wired to LLMPhase.references / AgentProfile.references. When a manifest
declares reference files, PhaseExecutor auto-mounts this tool so the LLM
can read them on demand instead of forcing large knowledge files into the
prompt.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE_BYTES = 200_000


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

    allowed_resolved: set[Path] = set()
    for raw_path in allowed_paths:
        path_clean = _clean_path(raw_path)
        if not path_clean:
            continue
        allowed_resolved.add((base_resolved / path_clean).resolve())
        allowed_resolved.add((references_root / path_clean).resolve())

    def _is_allowed(target: Path) -> bool:
        if target in allowed_resolved:
            return True
        try:
            target.relative_to(references_root)
            return True
        except ValueError:
            return False

    def read_file(ctx: dict[str, Any], path: str) -> str:
        """Read a reference file's contents."""
        del ctx
        try:
            path_clean = _clean_path(path)
            candidate_paths = [
                (base_resolved / path_clean).resolve(),
                (references_root / path_clean).resolve(),
            ]

            target: Path | None = None
            for candidate in candidate_paths:
                if candidate.exists() and candidate.is_file():
                    target = candidate
                    break

            if target is None:
                return (
                    f"[read_file Error] File not found: {path!r}. "
                    f"Available references: {allowed_paths}"
                )

            try:
                target.relative_to(base_resolved)
            except ValueError:
                return f"[read_file Error] Path escapes skill base_dir: {path!r}"

            if not _is_allowed(target):
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

            content = target.read_text(encoding="utf-8")
            logger.info("read_file: %s (%d bytes)", target, file_size)
            return content
        except Exception as exc:  # noqa: BLE001
            return f"[read_file Error] {type(exc).__name__}: {exc}"

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


__all__ = ["make_read_file_tool"]
