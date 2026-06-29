"""Local Git initialization helpers for Studio skill projects."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from app.core import config
from app.models.git_history import GitHistoryItem, GitHistoryKind

logger = logging.getLogger(__name__)
DEFAULT_GIT_TIMEOUT_SECONDS = 30
DEFAULT_LOCK_RETRY_DELAYS = (0.1, 0.3, 0.6)
EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
RELEASE_MARKER_TRAILER = "Studio-Release-Marker"
RELEASE_VERSION_TRAILER = "Studio-Release-Version"
RELEASE_ARTIFACT_ID_TRAILER = "Studio-Release-Artifact-Id"
RELEASE_CONTENT_HASH_TRAILER = "Studio-Release-Content-Hash"
RELEASE_MANIFEST_REF_TRAILER = "Studio-Release-Manifest-Ref"
RELEASE_SNAPSHOT_PREFIX = "release-"

STUDIO_GITIGNORE = "\n".join(
    [
        "/.workspace/*",
        "!/.workspace/golden/",
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

    _snapshot_lock_guard: ClassVar[threading.Lock] = threading.Lock()
    _snapshot_locks: ClassVar[dict[tuple[str, str], threading.Lock]] = {}

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_GIT_TIMEOUT_SECONDS,
        lock_retry_delays: tuple[float, ...] = DEFAULT_LOCK_RETRY_DELAYS,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.lock_retry_delays = lock_retry_delays

    @classmethod
    def _snapshot_lock(cls, skill_dir: Path, message: str) -> threading.Lock:
        key = (str(skill_dir.resolve()), message)
        with cls._snapshot_lock_guard:
            lock = cls._snapshot_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                cls._snapshot_locks[key] = lock
            return lock

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

    def commit(
        self, skill_dir: Path, message: str, *, allow_empty: bool = False
    ) -> GitCommandResult:
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        return run_git(
            skill_dir,
            *args,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )

    def commit_empty_snapshot(
        self,
        skill_dir: Path,
        message: str,
        *,
        trailers: Mapping[str, object] | None = None,
    ) -> str:
        expected_trailers = _normalize_commit_trailers(trailers)
        with self._snapshot_lock(skill_dir, message):
            existing = self.find_empty_snapshot_commit_with_exact_subject(
                skill_dir,
                message,
                trailers=expected_trailers,
            )
            if existing is not None:
                return existing

            last_cas_error: GitCommandError | None = None
            for _attempt in range(3):
                try:
                    return self._commit_empty_snapshot_once(
                        skill_dir,
                        message,
                        trailers=expected_trailers,
                    )
                except GitCommandError as exc:
                    if not _is_update_ref_cas_error(exc.result.stderr):
                        raise
                    last_cas_error = exc
                    existing = self.find_empty_snapshot_commit_with_exact_subject(
                        skill_dir,
                        message,
                        trailers=expected_trailers,
                    )
                    if existing is not None:
                        return existing
            if last_cas_error is not None:
                raise last_cas_error
            raise AssertionError("unreachable empty snapshot state")

    def _commit_empty_snapshot_once(
        self,
        skill_dir: Path,
        message: str,
        *,
        trailers: Mapping[str, str] | None = None,
    ) -> str:
        parent_args: list[str] = []
        tree_sha = EMPTY_TREE_SHA
        head_sha = ""
        try:
            head_sha = run_git(
                skill_dir,
                "rev-parse",
                "--verify",
                "HEAD^{commit}",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            ).stdout.strip()
        except GitCommandError as exc:
            if not _is_unborn_head_error(exc.result.stderr):
                raise
        else:
            tree_sha = run_git(
                skill_dir,
                "rev-parse",
                f"{head_sha}^{{tree}}",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            ).stdout.strip()
            parent_args = ["-p", head_sha]

        commit_args = ["commit-tree", tree_sha, *parent_args, "-m", message]
        trailer_body = _format_commit_trailers(trailers)
        if trailer_body:
            commit_args.extend(["-m", trailer_body])
        commit = run_git(
            skill_dir,
            *commit_args,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )
        marker_sha = commit.stdout.strip()
        run_git(
            skill_dir,
            "update-ref",
            "HEAD",
            marker_sha,
            head_sha,
            timeout_seconds=self.timeout_seconds,
            lock_retry_delays=self.lock_retry_delays,
        )
        return marker_sha

    def find_empty_snapshot_commit_with_exact_subject(
        self,
        skill_dir: Path,
        subject: str,
        *,
        trailers: Mapping[str, object] | None = None,
    ) -> str | None:
        expected_trailers = _normalize_commit_trailers(trailers)
        try:
            result = run_git(
                skill_dir,
                "log",
                "--format=%H%x1f%s%x1f%B%x1e",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            )
        except GitCommandError as exc:
            if _is_empty_or_damaged_history_error(exc.result.stderr):
                return None
            raise
        for record in result.stdout.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            fields = record.split("\x1f", 2)
            if len(fields) != 3:
                continue
            sha, message, body = fields
            if message != subject:
                continue
            if not self._is_empty_snapshot_commit(skill_dir, sha):
                continue
            if not _commit_message_has_trailers(body, expected_trailers):
                continue
            return sha
        return None

    def find_commit_with_exact_subject(self, skill_dir: Path, subject: str) -> str | None:
        try:
            result = run_git(
                skill_dir,
                "log",
                "--format=%H%x1f%s",
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            )
        except GitCommandError as exc:
            if _is_empty_or_damaged_history_error(exc.result.stderr):
                return None
            raise
        for row in result.stdout.splitlines():
            sha, separator, message = row.partition("\x1f")
            if separator and message == subject:
                return sha
        return None

    def _is_empty_snapshot_commit(self, skill_dir: Path, sha: str) -> bool:
        try:
            result = run_git(
                skill_dir,
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                "--root",
                sha,
                timeout_seconds=self.timeout_seconds,
                lock_retry_delays=self.lock_retry_delays,
            )
        except GitCommandError:
            return False
        return not result.stdout.strip()

    def has_commit_with_exact_subject(self, skill_dir: Path, subject: str) -> bool:
        return self.find_commit_with_exact_subject(skill_dir, subject) is not None

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
                "--pretty=format:%H%x1f%an%x1f%aI%x1f%s%x1f%B%x1e",
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
            fields = record.split("\x1f", 4)
            if len(fields) != 5:
                continue
            sha, author, timestamp_raw, message, body = fields
            release_marker = self._release_marker_metadata(skill_dir, sha, message, body)
            history.append(
                GitHistoryItem(
                    sha=sha,
                    message=message,
                    author=author,
                    timestamp=datetime.fromisoformat(timestamp_raw),
                    kind="release" if release_marker is not None else _history_kind(message),
                    release_version=release_marker.get("release_version") if release_marker else None,
                    artifact_id=release_marker.get("artifact_id") if release_marker else None,
                    content_hash=release_marker.get("content_hash") if release_marker else None,
                    manifest_ref=release_marker.get("manifest_ref") if release_marker else None,
                )
            )
        return history

    def _release_marker_metadata(
        self,
        skill_dir: Path,
        sha: str,
        subject: str,
        body: str,
    ) -> dict[str, str] | None:
        release_version = _release_version_from_marker_subject(subject)
        if release_version is None:
            return None
        trailers = _parse_commit_trailers(body)
        if trailers.get(RELEASE_MARKER_TRAILER, "").lower() != "true":
            return None
        if trailers.get(RELEASE_VERSION_TRAILER) != release_version:
            return None
        content_hash = trailers.get(RELEASE_CONTENT_HASH_TRAILER)
        manifest_ref = trailers.get(RELEASE_MANIFEST_REF_TRAILER)
        if not content_hash or not manifest_ref:
            return None
        if not self._is_empty_snapshot_commit(skill_dir, sha):
            return None
        marker = {
            "release_version": release_version,
            "content_hash": content_hash,
            "manifest_ref": manifest_ref,
        }
        artifact_id = trailers.get(RELEASE_ARTIFACT_ID_TRAILER)
        if artifact_id:
            marker["artifact_id"] = artifact_id
        return marker

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
                encoding="utf-8",
                errors="replace",
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
        or "your current branch" in lowered
        and "does not have any commits" in lowered
    )


def _is_unborn_head_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return _is_empty_or_damaged_history_error(stderr) or "needed a single revision" in lowered


def _is_update_ref_cas_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return "cannot lock ref" in lowered and "but expected" in lowered


def _is_revert_conflict_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return "conflict" in lowered or "merge" in lowered and "in progress" in lowered


def _normalize_commit_trailers(trailers: Mapping[str, object] | None) -> dict[str, str]:
    if not trailers:
        return {}
    normalized: dict[str, str] = {}
    for key, value in trailers.items():
        normalized_key = str(key).strip()
        normalized_value = " ".join(str(value).splitlines()).strip()
        if normalized_key and normalized_value:
            normalized[normalized_key] = normalized_value
    return normalized


def _format_commit_trailers(trailers: Mapping[str, str] | None) -> str:
    if not trailers:
        return ""
    return "\n".join(f"{key}: {value}" for key, value in trailers.items())


def _commit_message_has_trailers(message: str, expected: Mapping[str, str]) -> bool:
    if not expected:
        return True
    actual = _parse_commit_trailers(message)
    return all(actual.get(key) == value for key, value in expected.items())


def _parse_commit_trailers(message: str) -> dict[str, str]:
    trailers: dict[str, str] = {}
    for raw_line in message.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key:
            trailers[key] = value
    return trailers


def _release_version_from_marker_subject(subject: str) -> str | None:
    if not subject.startswith(RELEASE_SNAPSHOT_PREFIX):
        return None
    release_version = subject.removeprefix(RELEASE_SNAPSHOT_PREFIX)
    if release_version != release_version.strip() or any(char.isspace() for char in release_version):
        return None
    return release_version or None


def _history_kind(message: str) -> GitHistoryKind:
    if message.startswith("auto-run-"):
        return "auto_run"
    if message.startswith("manual-") or message.startswith("initial-"):
        return "manual"
    return "other"
