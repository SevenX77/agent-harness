from __future__ import annotations

from pathlib import Path

from app.services.git_local import GitLocalService
from fastapi.testclient import TestClient


def test_list_skill_summaries_includes_config_mismatch_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces_dir = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    local_git = GitLocalService()
    local_git.init(skill_dir)
    local_git.remote_add(
        skill_dir, "origin", "https://gitea.example.test/bob/text-segmentation.git"
    )
    settings_response = client.put(
        "/api/settings",
        json={"user_id": "alice", "gitea_host": "https://gitea.example.test"},
    )
    assert settings_response.status_code == 200

    response = client.get("/api/skills")

    assert response.status_code == 200
    skill = next(item for item in response.json() if item["id"] == "text-segmentation")
    assert skill["config_mismatch"] == {
        "actual_remote_url": "https://gitea.example.test/bob/text-segmentation.git",
        "expected_remote_url": "https://gitea.example.test/alice/text-segmentation.git",
        "recommendation": "建议以 .git/config 为基准 (per design.md 决策 22), 在 Settings 调整 User ID / Gitea Host",
    }
