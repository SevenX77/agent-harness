"""Covers wt-clean.sh's removal step: finish the job, and stay able to retry.

`git worktree remove` is not atomic: it drops the worktree registration before
the file delete finishes, so one held-open path (a dev server's CWD, a loaded
.pyd) leaves the directory on disk with no registration behind it. git then
resolves commands inside that leftover against the MAIN repo — `rev-parse
--abbrev-ref HEAD` answers "main" — so a cleanup keyed on the branch name skips
it as "is main" forever. That is how 59 unreachable trees and 48 GB accumulated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

WT_CLEAN = Path(__file__).resolve().parent / "wt-clean.sh"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, encoding="utf-8", check=True, capture_output=True).stdout


def _merged_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A repo whose worktree looks like a task whose PR merged and branch vanished."""
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)

    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "seed.txt")
    _git(repo, "commit", "-qm", "seed")
    _git(repo, "push", "-q", "origin", "HEAD:main")

    worktree = repo / ".worktrees" / "feat-done"
    _git(repo, "worktree", "add", "-q", "-b", "feat/done", str(worktree))
    # wt-ship pushes under the branch's own name; wt-clean requires that marker.
    _git(repo, "push", "-q", "-u", "origin", "feat/done")
    _git(repo, "push", "-q", "origin", "--delete", "feat/done")
    return repo, worktree


def _run_clean(repo: Path, target: str = "feat/done") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WT_CLEAN), target],
        cwd=repo,
        encoding="utf-8",
        check=False,
        capture_output=True,
    )


def _output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def _orphan(repo: Path, worktree: Path) -> None:
    """Reproduce what a failed `git worktree remove` leaves: no registration, dir intact."""
    admin = Path(_git(repo, "rev-parse", "--git-path", f"worktrees/{worktree.name}").strip())
    admin = admin if admin.is_absolute() else repo / admin
    subprocess.run(["rm", "-rf", str(admin)], check=True)
    assert worktree.exists()
    assert worktree.name not in _git(repo, "worktree", "list")


def test_removes_a_registered_merged_worktree(tmp_path: Path) -> None:
    repo, worktree = _merged_worktree(tmp_path)

    output = _output(_run_clean(repo))

    assert not worktree.exists(), f"worktree survived cleanup:\n{output}"
    assert "removed" in output, output


def test_removes_a_leftover_directory_whose_registration_is_gone(tmp_path: Path) -> None:
    """The half-finished-removal state must still be cleanable on a retry."""
    repo, worktree = _merged_worktree(tmp_path)
    _orphan(repo, worktree)

    output = _output(_run_clean(repo, target=".worktrees/feat-done"))

    assert not worktree.exists(), f"leftover directory was not cleaned — this is the state that accumulated:\n{output}"


def test_an_undeletable_leftover_is_reported_not_crashed_on(tmp_path: Path) -> None:
    """A delete that cannot succeed must still exit cleanly with actionable advice.

    `set -e` turns a failing rm into an abort, which would swallow the message
    telling the user what to close.
    """
    repo, worktree = _merged_worktree(tmp_path)
    _orphan(repo, worktree)

    with (worktree / "seed.txt").open("r+", encoding="utf-8"):
        result = _run_clean(repo, target=".worktrees/feat-done")
    output = _output(result)

    if not worktree.exists():
        pytest.skip("this platform deletes files that are still open")
    assert result.returncode == 0, f"script aborted instead of reporting:\n{output}"
    assert "could not remove" in output, output
    assert "still open" in output, output


def test_never_touches_the_main_worktree(tmp_path: Path) -> None:
    """The leftover path must not become a way to delete the repo itself."""
    repo, _ = _merged_worktree(tmp_path)

    output = _output(_run_clean(repo, target=str(repo)))

    assert (repo / "seed.txt").exists(), f"main worktree was damaged:\n{output}"
    assert "removed" not in output.replace("could not remove", ""), output
