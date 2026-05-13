"""Local Git initialization helpers for Studio skill projects."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core import config

logger = logging.getLogger(__name__)
DEFAULT_GIT_TIMEOUT_SECONDS = 30

STUDIO_GITIGNORE = "\n".join(
    [
        "/.workspace/*",
        "!/.workspace/golden/",
        "!/.workspace/predict/",
        "/.workspace/local_settings.json",
        "",
    ]
)
FALLBACK_USER_ID = "studio-user"


@dataclass(frozen=True)
class GitCommandResult:
    args: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout: str
    stderr: str


class GitCommandError(RuntimeError):
    """Raised when a local git command fails."""

    def __init__(self, result: GitCommandResult) -> None:
        self.result = result
        super().__init__(
            f"git {' '.join(result.args)} failed with exit code {result.returncode}: "
            f"{result.stderr.strip()}"
        )


class GitCommandTimeoutError(TimeoutError):
    """Raised when a local git command exceeds its timeout."""

    def __init__(self, *, args: tuple[str, ...], cwd: Path, timeout_seconds: float) -> None:
        self.args_tuple = args
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds
        super().__init__(f"git {' '.join(args)} timed out after {timeout_seconds}s")


class GitLocalService:
    """Small wrapper around local Git commands scoped to one skill repository."""

    def __init__(self, *, timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def init(self, skill_dir: Path) -> GitCommandResult:
        return run_git(skill_dir, "init", timeout_seconds=self.timeout_seconds)

    def add(self, skill_dir: Path, *paths: str, force: bool = False) -> GitCommandResult:
        args = ["add"]
        if force:
            args.append("-f")
        args.extend(paths or ("-A",))
        return run_git(skill_dir, *args, timeout_seconds=self.timeout_seconds)

    def commit(self, skill_dir: Path, message: str, *, allow_empty: bool = False) -> GitCommandResult:
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        return run_git(skill_dir, *args, timeout_seconds=self.timeout_seconds)

    def log(self, skill_dir: Path, *, limit: int = 50) -> list[str]:
        result = run_git(
            skill_dir,
            "log",
            "--oneline",
            f"-n{limit}",
            timeout_seconds=self.timeout_seconds,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def reset_hard(self, skill_dir: Path, sha: str) -> GitCommandResult:
        return run_git(skill_dir, "reset", "--hard", sha, timeout_seconds=self.timeout_seconds)

    def status(
        self,
        skill_dir: Path,
        *,
        ignored: bool = False,
        short: bool = True,
    ) -> GitCommandResult:
        args = ["status"]
        if short:
            args.append("--short")
        if ignored:
            args.append("--ignored")
        return run_git(skill_dir, *args, timeout_seconds=self.timeout_seconds)

    def auto_commit_run(self, skill_dir: Path, run_id: str) -> GitCommandResult | None:
        if not (skill_dir / ".git").exists():
            return None
        self.add(skill_dir)
        return self.commit(skill_dir, f"auto-run-{run_id}", allow_empty=True)


def initialize_skill_repository(skill_dir: Path, *, user_id: str | None = None) -> None:
    """Initialize local L1 Git state without touching global Git config."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    write_studio_gitignore(skill_dir)
    service = GitLocalService()
    service.init(skill_dir)
    resolved_user_id = user_id or _read_user_id_from_app_settings() or FALLBACK_USER_ID
    if resolved_user_id == FALLBACK_USER_ID:
        logger.warning("user_id missing, using fallback")
    run_git(skill_dir, "config", "--local", "user.name", resolved_user_id)
    run_git(skill_dir, "config", "--local", "user.email", f"{resolved_user_id}@studio.local")
    service.add(skill_dir)
    if service.status(skill_dir).stdout.strip():
        service.commit(skill_dir, "initial-skill")


def write_studio_gitignore(skill_dir: Path) -> Path:
    """Write the Studio P0 .gitignore template for a skill repository."""
    gitignore_path = skill_dir / ".gitignore"
    gitignore_path.write_text(STUDIO_GITIGNORE, encoding="utf-8")
    return gitignore_path


def _read_user_id_from_app_settings() -> str | None:
    settings_path = config.APP_SETTINGS_PATH
    if not settings_path.exists():
        return None
    try:
        payload: Any = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("user_id", "User ID", "userId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def run_git(
    skill_dir: Path,
    *args: str,
    timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS,
) -> GitCommandResult:
    if not skill_dir.exists():
        raise FileNotFoundError(f"Git cwd does not exist: {skill_dir}")
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=skill_dir,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitCommandTimeoutError(
            args=tuple(args),
            cwd=skill_dir,
            timeout_seconds=timeout_seconds,
        ) from exc
    result = GitCommandResult(
        args=tuple(args),
        cwd=skill_dir,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if completed.returncode != 0:
        raise GitCommandError(result)
    return result
