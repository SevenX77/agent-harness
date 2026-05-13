"""Local Git initialization helpers for Studio skill projects."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import config
from app.models.git_history import GitHistoryItem, GitHistoryKind

logger = logging.getLogger(__name__)
DEFAULT_GIT_TIMEOUT_SECONDS = 30
DEFAULT_LOCK_RETRY_DELAYS = (0.1, 0.3, 0.6)

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


class GitFileLockedError(GitCommandError):
    """Raised when Git index lock contention persists after retries."""

    error_code = "GIT_FILE_LOCKED"


class GitObjectNotFoundError(GitCommandError):
    """Raised when a requested commit object does not exist."""

    error_code = "GIT_OBJECT_NOT_FOUND"


class GitRevertConflictError(GitCommandError):
    """Raised when a revert/reset cannot proceed cleanly."""

    error_code = "GIT_REVERT_CONFLICT"


class GitLocalService:
    """Small wrapper around local Git commands scoped to one skill repository."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS,
        lock_retry_delays: tuple[float, ...] = DEFAULT_LOCK_RETRY_DELAYS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.lock_retry_delays = lock_retry_delays

    def init(self, skill_dir: Path) -> GitCommandResult:
        return run_git(
            skill_dir,
            "init",
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def add(self, skill_dir: Path, *paths: str, force: bool = False) -> GitCommandResult:
        args = ["add"]
        if force:
            args.append("-f")
        args.extend(paths or ("-A",))
        return run_git(
            skill_dir,
            *args,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def force_add_path(self, skill_dir: Path, path: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "add",
            "-f",
            path,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def create_branch(self, skill_dir: Path, branch: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "checkout",
            "-b",
            branch,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def commit(self, skill_dir: Path, message: str, *, allow_empty: bool = False) -> GitCommandResult:
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        return run_git(
            skill_dir,
            *args,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def log(self, skill_dir: Path, *, limit: int = 50) -> list[str]:
        result = run_git(
            skill_dir,
            "log",
            "--oneline",
            f"-n{limit}",
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )
        return [line for line in result.stdout.splitlines() if line.strip()]

    def list_history(self, skill_dir: Path, *, limit: int = 100) -> list[GitHistoryItem]:
        try:
            result = run_git(
                skill_dir,
                "log",
                f"-n{limit}",
                "--pretty=format:%H%x1f%an%x1f%aI%x1f%s%x1e",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            )
        except GitCommandError as exc:
            if _is_empty_or_damaged_history_error(exc.result.stderr):
                return []
            raise

        history: list[GitHistoryItem] = []
        for record in result.stdout.split("\x1e"):
            record = record.strip()
            if not record:
                continue
            fields = record.split("\x1f")
            if len(fields) != 4:
                continue
            sha, author, timestamp_raw, message = fields
            history.append(
                GitHistoryItem(
                    sha=sha,
                    message=message,
                    author=author,
                    timestamp=datetime.fromisoformat(timestamp_raw),
                    kind=_history_kind(message),
                )
            )
        return history

    def reset_hard(self, skill_dir: Path, sha: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "reset",
            "--hard",
            sha,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def remote_get_url(self, skill_dir: Path, remote: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "remote",
            "get-url",
            remote,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def remote_add(self, skill_dir: Path, remote: str, url: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "remote",
            "add",
            remote,
            url,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def remote_set_url(self, skill_dir: Path, remote: str, url: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "remote",
            "set-url",
            remote,
            url,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def push(self, skill_dir: Path, remote: str, branch: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "push",
            remote,
            branch,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def pull(self, skill_dir: Path, remote: str, branch: str) -> GitCommandResult:
        return run_git(
            skill_dir,
            "pull",
            "--ff-only",
            remote,
            branch,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def revert_to(self, skill_dir: Path, sha: str) -> GitCommandResult:
        try:
            run_git(
                skill_dir,
                "cat-file",
                "-e",
                f"{sha}^{{commit}}",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            )
        except GitCommandError as exc:
            raise GitObjectNotFoundError(exc.result) from exc

        status = self.status(skill_dir)
        if status.stdout.strip():
            logger.warning("reverting with uncommitted changes in %s", skill_dir)
        try:
            return self.reset_hard(skill_dir, sha)
        except GitCommandError as exc:
            if _is_revert_conflict_error(exc.result.stderr):
                raise GitRevertConflictError(exc.result) from exc
            raise

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
        return run_git(
            skill_dir,
            *args,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

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
    lock_retry_delays: tuple[float, ...] = DEFAULT_LOCK_RETRY_DELAYS,
) -> GitCommandResult:
    if not skill_dir.exists():
        raise FileNotFoundError(f"Git cwd does not exist: {skill_dir}")
    result: GitCommandResult | None = None
    for attempt in range(len(lock_retry_delays) + 1):
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
        if completed.returncode == 0:
            return result
        if not _is_lock_error(completed.stderr):
            raise GitCommandError(result)
        if attempt < len(lock_retry_delays):
            time.sleep(lock_retry_delays[attempt])
            continue
        raise GitFileLockedError(result)
    raise AssertionError("unreachable git retry state")


def _is_lock_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return "index.lock" in lowered or "unable to create" in lowered and ".git/index.lock" in lowered


def _is_empty_or_damaged_history_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return (
        "does not have any commits yet" in lowered
        or "bad default revision" in lowered
        or "not a git repository" in lowered
        or "bad object head" in lowered
        or "your current branch" in lowered and "does not have any commits" in lowered
    )


def _is_revert_conflict_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return "conflict" in lowered or "merge" in lowered and "in progress" in lowered


def _history_kind(message: str) -> GitHistoryKind:
    if message.startswith("auto-run-"):
        return "auto_run"
    if message.startswith("manual-") or message.startswith("initial-"):
        return "manual"
    return "other"
