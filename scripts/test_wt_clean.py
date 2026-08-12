"""Guards the ignore rules that decide whether a finished worktree is cleanable.

`scripts/wt-clean.sh` refuses to remove a worktree whose `git status` is dirty,
so any build artifact that escapes `.gitignore` pins that worktree on disk
forever. Vite writes its dependency cache to `apps/studio/frontend/.vite/`, so a
root-anchored `/.vite/` pattern silently fails to cover it — the defect that let
48 GB of previewed-but-never-cleaned worktrees accumulate.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VITE_CACHE = "apps/studio/frontend/.vite/deps/_metadata.json"


def test_vite_dep_cache_is_ignored() -> None:
    """The real repo must ignore the cache at the depth Vite actually writes it."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", VITE_CACHE],
        cwd=REPO_ROOT,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, (
        f"{VITE_CACHE} is not ignored — a previewed worktree stays dirty forever and wt-clean.sh will skip it"
    )


def test_previewed_worktree_reports_clean(tmp_path: Path) -> None:
    """A tree holding only the Vite cache must look clean to `git status`.

    Exercises the pattern's semantics against a real git, rather than asserting
    on the text of .gitignore.
    """

    def run(*args: str) -> None:
        subprocess.run(args, cwd=tmp_path, encoding="utf-8", check=True, capture_output=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "test")

    (tmp_path / ".gitignore").write_text((REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    run("git", "add", ".gitignore")
    run("git", "commit", "-qm", "baseline")

    cache = tmp_path / VITE_CACHE
    cache.parent.mkdir(parents=True)
    cache.write_text("{}", encoding="utf-8")

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=tmp_path,
        encoding="utf-8",
        check=True,
        capture_output=True,
    )
    assert status.stdout == "", (
        f"Vite cache leaks into git status: {status.stdout!r} — wt-clean.sh would "
        "skip this worktree as having uncommitted changes"
    )
