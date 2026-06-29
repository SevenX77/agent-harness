from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from app.core import config
from app.services.git_local import GitLocalService
from fastapi.testclient import TestClient

from tests.test_api import _agent_skill_content, _agent_skill_files


def test_skill_history_empty_repo_returns_empty(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "empty-history", "files": _agent_skill_files("empty-history")},
    )
    skill_dir = config.DEFAULT_SKILLS_ROOT / "empty-history"
    _remove_git_dir(skill_dir)
    GitLocalService().init(skill_dir)

    response = client.get("/api/skills/empty-history/history")

    assert response.status_code == 200
    assert response.json() == []


def test_skill_history_lists_commits_newest_first(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "history-skill", "files": _agent_skill_files("history-skill")},
    )
    skill_dir = config.DEFAULT_SKILLS_ROOT / "history-skill"
    _git(skill_dir, "commit", "--allow-empty", "-m", "auto-run-old")
    _git(skill_dir, "commit", "--allow-empty", "-m", "auto-run-new")

    response = client.get("/api/skills/history-skill/history")

    assert response.status_code == 200
    body = response.json()
    assert [item["message"] for item in body[:2]] == ["auto-run-new", "auto-run-old"]
    assert body[0]["kind"] == "auto_run"
    assert body[0]["sha"]
    assert body[0]["author"] == "studio-user"


def test_skill_history_handles_utf8_commit_messages(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "history-utf8-skill", "files": _agent_skill_files("history-utf8-skill")},
    )
    skill_dir = config.DEFAULT_SKILLS_ROOT / "history-utf8-skill"
    _git(skill_dir, "commit", "--allow-empty", "-m", "manual-中文-🤖")

    response = client.get("/api/skills/history-utf8-skill/history")

    assert response.status_code == 200
    assert response.json()[0]["message"] == "manual-中文-🤖"


def test_skill_history_damaged_git_returns_empty(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "damaged-history", "files": _agent_skill_files("damaged-history")},
    )
    skill_dir = config.DEFAULT_SKILLS_ROOT / "damaged-history"
    (skill_dir / ".git" / "HEAD").write_text("ref: refs/heads/missing\n", encoding="utf-8")

    response = client.get("/api/skills/damaged-history/history")

    assert response.status_code == 200
    assert response.json() == []


def test_revert_restores_skill_file_to_old_commit(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "revert-skill", "files": _agent_skill_files("revert-skill")},
    )
    skill_dir = config.DEFAULT_SKILLS_ROOT / "revert-skill"
    old_sha = _git(skill_dir, "rev-parse", "HEAD").stdout.strip()
    skill_path = skill_dir / "GRAPH.md"
    skill_path.write_text(
        _agent_skill_content("revert-skill").replace(
            "description: Draft structured ideas",
            "description: Changed ideas",
        ),
        encoding="utf-8",
    )
    _git(skill_dir, "add", "GRAPH.md")
    _git(skill_dir, "commit", "-m", "manual-change")

    response = client.post("/api/skills/revert-skill/revert", json={"sha": old_sha})

    assert response.status_code == 200
    assert response.json()["manifest"]["description"] == "Draft structured ideas"
    assert "description: Draft structured ideas" in skill_path.read_text(encoding="utf-8")


def test_revert_missing_sha_returns_404(client: TestClient) -> None:
    client.post(
        "/api/skills",
        json={"skill_id": "missing-revert", "files": _agent_skill_files("missing-revert")},
    )

    response = client.post("/api/skills/missing-revert/revert", json={"sha": "0" * 40})

    assert response.status_code == 404
    assert response.json()["error_code"] == "GIT_OBJECT_NOT_FOUND"


def _git(skill_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=skill_dir,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _remove_git_dir(skill_dir: Path) -> None:
    def retry_writable(function: object, path: str, _exc_info: object) -> None:
        Path(path).chmod(0o700)
        function(path)  # type: ignore[operator]

    shutil.rmtree(skill_dir / ".git", onerror=retry_writable)
