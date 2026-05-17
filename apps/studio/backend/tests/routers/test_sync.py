from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from app.core.backends import get_git_collab
from app.services.git_collab import CollaborateResult
from fastapi.testclient import TestClient


def test_sync_save_to_team_routes_to_service(client: TestClient) -> None:
    fake = FakeGitCollaborate()
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    _write_settings(client)

    response = client.post(
        "/api/skills/text-segmentation/sync",
        json={"action": "save_to_team"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake.calls == [
        {
            "method": "save_to_team",
            "owner": "alice",
            "repo": "text-segmentation",
            "branch": "main",
        }
    ]


def test_sync_sync_from_team_routes_to_service(client: TestClient) -> None:
    fake = FakeGitCollaborate()
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    _write_settings(client)

    response = client.post(
        "/api/skills/text-segmentation/sync",
        json={"action": "sync_from_team", "branch": "main"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert fake.calls == [
        {
            "method": "sync_from_team",
            "owner": "alice",
            "repo": "text-segmentation",
            "branch": "main",
        }
    ]


def test_sync_submit_for_review_routes_to_service(client: TestClient) -> None:
    fake = FakeGitCollaborate()
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    _write_settings(client)

    response = client.post(
        "/api/skills/text-segmentation/sync",
        json={
            "action": "submit_for_review",
            "dev_branch": "dev/alice/text-segmentation",
            "pr_title": "Update text segmentation",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["pr_url"] == "https://gitea.example.com/alice/text-segmentation/pulls/1"
    assert fake.calls == [
        {
            "method": "submit_for_review",
            "owner": "alice",
            "repo": "text-segmentation",
            "dev_branch": "dev/alice/text-segmentation",
            "base": "main",
            "pr_title": "Update text segmentation",
        }
    ]


def test_sync_400_when_user_id_missing(client: TestClient) -> None:
    fake = FakeGitCollaborate()
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    response = client.put(
        "/api/settings",
        json={"user_id": "", "gitea_host": "https://gitea.example.com"},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/skills/text-segmentation/sync",
        json={"action": "save_to_team"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "APP_SETTINGS_INCOMPLETE"
    assert fake.calls == []


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"action": "submit_for_review", "pr_title": "Update text segmentation"}, "dev_branch"),
        ({"action": "submit_for_review", "dev_branch": "dev/alice/text-segmentation"}, "pr_title"),
    ],
)
def test_sync_400_when_submit_for_review_missing_fields(
    client: TestClient,
    payload: dict[str, str],
    field: str,
) -> None:
    fake = FakeGitCollaborate()
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    _write_settings(client)

    response = client.post("/api/skills/text-segmentation/sync", json=payload)

    assert response.status_code == 400
    assert response.json()["error_code"] == "MISSING_REQUIRED_FIELD"
    assert response.json()["details"] == {"field": field}
    assert fake.calls == []


def test_sync_propagates_requires_review_status(client: TestClient) -> None:
    fake = FakeGitCollaborate(
        save_result=CollaborateResult(
            status="requires_review",
            message="Push requires review permissions",
        ),
    )
    client.app.dependency_overrides[get_git_collab] = lambda: fake
    _write_settings(client)

    response = client.post(
        "/api/skills/text-segmentation/sync",
        json={"action": "save_to_team"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "requires_review"


class FakeGitea:
    def __init__(self) -> None:
        self.host = ""


class FakeGitCollaborate:
    def __init__(self, *, save_result: CollaborateResult | None = None) -> None:
        self.gitea_host = ""
        self.gitea = FakeGitea()
        self.save_result = save_result or CollaborateResult(status="ok", message="saved")
        self.calls: list[dict[str, Any]] = []

    def save_to_team(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
    ) -> CollaborateResult:
        del skill_dir
        self.calls.append(
            {"method": "save_to_team", "owner": owner, "repo": repo, "branch": branch}
        )
        return self.save_result

    def sync_from_team(
        self,
        skill_dir: Path,
        *,
        owner: str,
        repo: str,
        branch: str = "main",
    ) -> CollaborateResult:
        del skill_dir
        self.calls.append(
            {"method": "sync_from_team", "owner": owner, "repo": repo, "branch": branch}
        )
        return CollaborateResult(status="ok", message="synced")

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
        del skill_dir
        self.calls.append(
            {
                "method": "submit_for_review",
                "owner": owner,
                "repo": repo,
                "dev_branch": dev_branch,
                "base": base,
                "pr_title": pr_title,
            }
        )
        return CollaborateResult(
            status="ok",
            message="submitted",
            pr_url="https://gitea.example.com/alice/text-segmentation/pulls/1",
        )


def _write_settings(client: TestClient) -> None:
    response = client.put(
        "/api/settings",
        json={"user_id": "alice", "gitea_host": "https://gitea.example.com"},
    )
    assert response.status_code == 200
