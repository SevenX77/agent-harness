from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services.git_collab import GiteaApiError, GiteaClient, GitCollaborateService
from app.services.git_local import GitCommandError, GitCommandResult, GitLocalService, run_git


def test_gitea_create_repo_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/user/repos"
        assert request.headers["Authorization"] == "token test-token"
        assert request.read() == b'{"name":"skill-repo","private":true}'
        return httpx.Response(200, json={"name": "skill-repo", "private": True})

    client = GiteaClient(
        host="https://gitea.example.test",
        token="test-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.create_repo("skill-repo", owner="alice") == {
        "name": "skill-repo",
        "private": True,
    }


def test_gitea_create_repo_4xx_raises_GiteaApiError() -> None:
    client = GiteaClient(
        host="https://gitea.example.test",
        token="bad-token",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(403, text="forbidden")),
        ),
    )

    with pytest.raises(GiteaApiError) as exc_info:
        client.create_repo("skill-repo", owner="alice")

    assert exc_info.value.status_code == 403
    assert exc_info.value.body == "forbidden"


def test_save_to_team_pushes_main_success(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit()
    service = _service(local_git)

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.status == "ok"
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("remote_add", "origin", "https://gitea.example.test/alice/skill-repo.git"),
        ("push", "origin", "main"),
    ]


def test_save_to_team_403_returns_requires_review(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(push_error="remote: 403 forbidden")
    service = _service(local_git)

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.status == "requires_review"
    assert result.pr_url == "https://gitea.example.test/alice/skill-repo/pulls/1"
    assert result.extra["dev_branch"].startswith("team-save/alice-")


def test_save_to_team_force_adds_latest_when_present(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    latest_dir = skill_dir / ".workspace" / "runs" / "latest"
    latest_dir.mkdir(parents=True)
    (latest_dir / "run_metadata.json").write_text("{}", encoding="utf-8")
    local_git = RecordingGit(existing_remote="https://gitea.example.test/alice/skill-repo.git")
    service = _service(local_git)

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.extra["latest_included"] is True
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("force_add_path", ".workspace/runs/latest"),
        ("commit", "team-save: include latest snapshot", "allow_empty=False"),
        ("push", "origin", "main"),
    ]


def test_save_to_team_skips_latest_when_absent(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(existing_remote="https://gitea.example.test/alice/skill-repo.git")
    service = _service(local_git)

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.extra["latest_included"] is False
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("push", "origin", "main"),
    ]


def test_save_to_team_main_protected_falls_back_to_pr(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(
        existing_remote="https://gitea.example.test/alice/skill-repo.git",
        push_error="remote: error: GH013: Repository rule violations found",
    )
    gitea = RecordingGitea(
        host="https://gitea.example.test",
        token="test-token",
        pr={"html_url": "https://gitea.example.test/alice/skill-repo/pulls/2"},
    )
    service = GitCollaborateService(
        local_git=local_git,
        gitea=gitea,
        gitea_host="https://gitea.example.test",
    )

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    dev_branch = result.extra["dev_branch"]
    assert result.status == "requires_review"
    assert result.pr_url == "https://gitea.example.test/alice/skill-repo/pulls/2"
    assert isinstance(dev_branch, str)
    assert dev_branch.startswith("team-save/alice-")
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("push", "origin", "main"),
        ("create_branch", dev_branch),
        ("push", "origin", dev_branch),
    ]
    assert gitea.pull_requests == [
        {
            "owner": "alice",
            "repo": "skill-repo",
            "title_prefix": "[Save to Team] alice - ",
            "head": dev_branch,
            "base": "main",
        }
    ]


def test_save_to_team_fallback_pr_creation_fails_returns_error(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(
        existing_remote="https://gitea.example.test/alice/skill-repo.git",
        push_error="remote: 403 forbidden",
    )
    gitea = RecordingGitea(
        host="https://gitea.example.test",
        token="test-token",
        pr_error=GiteaApiError(status_code=500, body="server error"),
    )
    service = GitCollaborateService(
        local_git=local_git,
        gitea=gitea,
        gitea_host="https://gitea.example.test",
    )

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.status == "error"
    assert "Failed to open review fallback" in result.message
    assert "server error" in result.message
    assert result.extra["dev_branch"].startswith("team-save/alice-")


def test_save_to_team_main_push_success_no_fallback(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(existing_remote="https://gitea.example.test/alice/skill-repo.git")
    gitea = RecordingGitea(
        host="https://gitea.example.test",
        token="test-token",
        pr={"html_url": "https://gitea.example.test/alice/skill-repo/pulls/3"},
    )
    service = GitCollaborateService(
        local_git=local_git,
        gitea=gitea,
        gitea_host="https://gitea.example.test",
    )

    result = service.save_to_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.status == "ok"
    assert result.pr_url is None
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("push", "origin", "main"),
    ]
    assert gitea.pull_requests == []


def test_sync_from_team_pulls(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(existing_remote="https://gitea.example.test/alice/skill-repo.git")
    service = _service(local_git)

    result = service.sync_from_team(skill_dir, owner="alice", repo="skill-repo")

    assert result.status == "ok"
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("pull", "origin", "main"),
    ]


def test_submit_for_review_creates_pr(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = RecordingGit(existing_remote="https://gitea.example.test/alice/skill-repo.git")
    gitea = RecordingGitea(
        host="https://gitea.example.test",
        token="test-token",
        pr={"html_url": "https://gitea.example.test/alice/skill-repo/pulls/1"},
    )
    service = GitCollaborateService(
        local_git=local_git,
        gitea=gitea,
        gitea_host="https://gitea.example.test",
    )

    result = service.submit_for_review(
        skill_dir,
        owner="alice",
        repo="skill-repo",
        dev_branch="dev/alice/change",
        pr_title="Update skill",
    )

    assert result.status == "ok"
    assert result.pr_url == "https://gitea.example.test/alice/skill-repo/pulls/1"
    assert local_git.calls == [
        ("remote_get_url", "origin"),
        ("push", "origin", "dev/alice/change"),
    ]
    assert gitea.pull_requests == [
        {
            "owner": "alice",
            "repo": "skill-repo",
            "title_prefix": "Update skill",
            "head": "dev/alice/change",
            "base": "main",
        }
    ]


class RecordingGit(GitLocalService):
    def __init__(
        self,
        *,
        existing_remote: str | None = None,
        push_error: str | None = None,
    ) -> None:
        super().__init__()
        self.existing_remote = existing_remote
        self.push_error = push_error
        self.calls: list[tuple[str, ...]] = []

    def remote_get_url(self, skill_dir: Path, remote: str) -> GitCommandResult:
        self.calls.append(("remote_get_url", remote))
        if self.existing_remote is None:
            raise GitCommandError(_result(skill_dir, ("remote", "get-url", remote), returncode=2))
        return _result(skill_dir, ("remote", "get-url", remote), stdout=f"{self.existing_remote}\n")

    def remote_add(self, skill_dir: Path, remote: str, url: str) -> GitCommandResult:
        self.calls.append(("remote_add", remote, url))
        self.existing_remote = url
        return _result(skill_dir, ("remote", "add", remote, url))

    def remote_set_url(self, skill_dir: Path, remote: str, url: str) -> GitCommandResult:
        self.calls.append(("remote_set_url", remote, url))
        self.existing_remote = url
        return _result(skill_dir, ("remote", "set-url", remote, url))

    def force_add_path(self, skill_dir: Path, path: str) -> GitCommandResult:
        self.calls.append(("force_add_path", path))
        return _result(skill_dir, ("add", "-f", path))

    def commit(self, skill_dir: Path, message: str, *, allow_empty: bool = False) -> GitCommandResult:
        self.calls.append(("commit", message, f"allow_empty={allow_empty}"))
        return _result(skill_dir, ("commit", "-m", message))

    def create_branch(self, skill_dir: Path, branch: str) -> GitCommandResult:
        self.calls.append(("create_branch", branch))
        return _result(skill_dir, ("checkout", "-b", branch))

    def push(self, skill_dir: Path, remote: str, branch: str) -> GitCommandResult:
        self.calls.append(("push", remote, branch))
        if self.push_error is not None and branch == "main":
            raise GitCommandError(
                _result(skill_dir, ("push", remote, branch), returncode=1, stderr=self.push_error),
            )
        return _result(skill_dir, ("push", remote, branch))

    def pull(self, skill_dir: Path, remote: str, branch: str) -> GitCommandResult:
        self.calls.append(("pull", remote, branch))
        return _result(skill_dir, ("pull", "--ff-only", remote, branch))


class RecordingGitea(GiteaClient):
    def __init__(
        self,
        *,
        host: str,
        token: str,
        pr: dict[str, str] | None = None,
        pr_error: GiteaApiError | None = None,
    ) -> None:
        super().__init__(host=host, token=token)
        self.pr = pr or {"html_url": "https://gitea.example.test/alice/skill-repo/pulls/1"}
        self.pr_error = pr_error
        self.pull_requests: list[dict[str, str | None]] = []

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
    ) -> dict[str, str]:
        if self.pr_error is not None:
            raise self.pr_error
        self.pull_requests.append(
            {
                "owner": owner,
                "repo": repo,
                "title_prefix": title[:23],
                "head": head,
                "base": base,
            },
        )
        return self.pr


def _service(local_git: GitLocalService) -> GitCollaborateService:
    return GitCollaborateService(
        local_git=local_git,
        gitea=RecordingGitea(host="https://gitea.example.test", token="test-token"),
        gitea_host="https://gitea.example.test",
    )


def _init_repo(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    local_git = GitLocalService()
    local_git.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@example.test")
    local_git.add(skill_dir)
    local_git.commit(skill_dir, "initial", allow_empty=True)
    return skill_dir


def _result(
    cwd: Path,
    args: tuple[str, ...],
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> GitCommandResult:
    return GitCommandResult(
        args=args,
        cwd=cwd,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
