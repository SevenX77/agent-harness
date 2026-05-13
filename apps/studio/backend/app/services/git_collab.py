"""Git L2 collaboration helpers for Studio skill repositories."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.services.git_local import GitCommandError, GitLocalService

LATEST_RUN_PATH = ".workspace/runs/latest"
TEAM_SAVE_COMMIT_MESSAGE = "team-save: include latest snapshot"

logger = logging.getLogger(__name__)

CollaborateStatus = Literal["ok", "requires_review", "conflict", "error"]


class CollaborateResult(BaseModel):
    """Business-facing result for L2 collaboration actions."""

    model_config = ConfigDict(extra="forbid")

    status: CollaborateStatus
    message: str
    pr_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GiteaApiError(RuntimeError):
    """Raised when Gitea returns a non-success HTTP status."""

    def __init__(self, *, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Gitea API returned {status_code}: {body}")


class GiteaClient:
    """Small synchronous client for the Gitea REST API."""

    def __init__(
        self,
        host: str,
        token: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self._http = http_client or httpx.Client()

    def create_repo(self, name: str, owner: str, private: bool = True) -> dict[str, Any]:
        del owner
        return self._request(
            "POST",
            "/api/v1/user/repos",
            json={"name": name, "private": private},
        )

    def create_branch(self, owner: str, repo: str, branch: str, from_ref: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/repos/{owner}/{repo}/branches",
            json={"new_branch_name": branch, "old_ref_name": from_ref},
        )

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/repos/{owner}/{repo}/pulls",
            json={"title": title, "head": head, "base": base},
        )

    def _request(self, method: str, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        if not self.host:
            raise ValueError("Gitea host is not configured")
        if not self.token:
            raise ValueError("Gitea token is not configured")

        response = self._http.request(
            method,
            f"{self.host}{path}",
            headers={"Authorization": f"token {self.token}"},
            json=json,
        )
        if response.status_code >= 400:
            raise GiteaApiError(status_code=response.status_code, body=response.text)
        payload = response.json()
        if not isinstance(payload, dict):
            raise GiteaApiError(status_code=response.status_code, body=response.text)
        return payload


class GitCollaborateService:
    """Coordinate local git commands and Gitea collaboration actions."""

    def __init__(
        self,
        local_git: GitLocalService,
        gitea: GiteaClient,
        gitea_host: str,
    ) -> None:
        self.local_git = local_git
        self.gitea = gitea
        self.gitea_host = gitea_host.rstrip("/")

    def save_to_team(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
    ) -> CollaborateResult:
        self._ensure_origin(skill_dir, owner=owner, repo=repo)
        latest_included = self._include_latest_snapshot(skill_dir)
        try:
            self.local_git.push(skill_dir, "origin", branch)
        except GitCommandError as exc:
            if _is_permission_denied(exc):
                logger.warning("main push 403, fallback to dev branch + PR")
                return self._fallback_to_review(
                    skill_dir,
                    owner=owner,
                    repo=repo,
                    base=branch,
                    latest_included=latest_included,
                )
            raise
        return CollaborateResult(
            status="ok",
            message=f"Pushed {branch} to team",
            extra={"latest_included": latest_included},
        )

    def sync_from_team(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
    ) -> CollaborateResult:
        self._ensure_origin(skill_dir, owner=owner, repo=repo)
        try:
            self.local_git.pull(skill_dir, "origin", branch)
        except GitCommandError as exc:
            if _is_conflict(exc):
                return CollaborateResult(status="conflict", message="Pull requires conflict resolution")
            raise
        return CollaborateResult(status="ok", message=f"Pulled {branch} from team")

    def submit_for_review(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        dev_branch: str,
        pr_title: str,
        base: str = "main",
    ) -> CollaborateResult:
        self._ensure_origin(skill_dir, owner=owner, repo=repo)
        self.local_git.push(skill_dir, "origin", dev_branch)
        pr = self.gitea.create_pull_request(
            owner=owner,
            repo=repo,
            title=pr_title,
            head=dev_branch,
            base=base,
        )
        pr_url = _pr_url(pr)
        return CollaborateResult(
            status="ok",
            message="Submitted for review",
            pr_url=pr_url,
            extra={"pull_request": pr},
        )

    def _ensure_origin(self, skill_dir: Path, *, owner: str, repo: str) -> None:
        remote_url = self._remote_url(owner=owner, repo=repo)
        try:
            current = self.local_git.remote_get_url(skill_dir, "origin").stdout.strip()
        except GitCommandError:
            self.local_git.remote_add(skill_dir, "origin", remote_url)
            return
        if current != remote_url:
            self.local_git.remote_set_url(skill_dir, "origin", remote_url)

    def _remote_url(self, *, owner: str, repo: str) -> str:
        if not self.gitea_host:
            raise ValueError("Gitea host is not configured")
        return f"{self.gitea_host}/{owner}/{repo}.git"

    def _include_latest_snapshot(self, skill_dir: Path) -> bool:
        if not (skill_dir / LATEST_RUN_PATH).exists():
            return False
        logger.info("force-adding latest run snapshot before team save")
        self.local_git.force_add_path(skill_dir, LATEST_RUN_PATH)
        try:
            self.local_git.commit(skill_dir, TEAM_SAVE_COMMIT_MESSAGE)
        except GitCommandError as exc:
            if _is_empty_commit(exc):
                return True
            raise
        return True

    def _fallback_to_review(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        base: str,
        latest_included: bool,
    ) -> CollaborateResult:
        dev_branch = _team_save_branch(owner)
        title = _fallback_pr_title(owner)
        try:
            logger.info("creating fallback branch %s", dev_branch)
            self.local_git.create_branch(skill_dir, dev_branch)
            logger.info("pushing fallback branch %s", dev_branch)
            self.local_git.push(skill_dir, "origin", dev_branch)
            logger.info("creating fallback PR for %s -> %s", dev_branch, base)
            pr = self.gitea.create_pull_request(
                owner=owner,
                repo=repo,
                title=title,
                head=dev_branch,
                base=base,
            )
        except Exception as exc:
            logger.exception("save_to_team fallback to review failed")
            return CollaborateResult(
                status="error",
                message=f"Failed to open review fallback: {exc}",
                extra={"dev_branch": dev_branch, "latest_included": latest_included},
            )

        return CollaborateResult(
            status="requires_review",
            message="Main protected, opened PR for review",
            pr_url=_pr_url(pr),
            extra={"dev_branch": dev_branch, "latest_included": latest_included},
        )


def _is_permission_denied(exc: GitCommandError) -> bool:
    text = f"{exc.result.stdout}\n{exc.result.stderr}".lower()
    return (
        "403" in text
        or "permission denied" in text
        or "forbidden" in text
        or "gh013" in text
        or "protected branch" in text
        or "repository rule violations" in text
        or "remote rejected" in text
    )


def _is_conflict(exc: GitCommandError) -> bool:
    text = f"{exc.result.stdout}\n{exc.result.stderr}".lower()
    return "conflict" in text or "non-fast-forward" in text or "not possible to fast-forward" in text


def _is_empty_commit(exc: GitCommandError) -> bool:
    text = f"{exc.result.stdout}\n{exc.result.stderr}".lower()
    return "nothing to commit" in text or "no changes added to commit" in text


def _team_save_branch(owner: str) -> str:
    safe_owner = "".join(char if char.isalnum() or char in "._-" else "-" for char in owner)
    return f"team-save/{safe_owner}-{int(time.time())}"


def _fallback_pr_title(owner: str) -> str:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    return f"[Save to Team] {owner} - {timestamp}"


def _pr_url(payload: dict[str, Any]) -> str | None:
    for key in ("html_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
