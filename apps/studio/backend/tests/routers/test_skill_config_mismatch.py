from __future__ import annotations

import asyncio
from pathlib import Path

from app.core import config
from app.core.adapters.metadata_local import LocalJsonMetadataStore
from app.services.git_local import GitLocalService
from fastapi.testclient import TestClient


def test_list_skill_summaries_includes_config_mismatch_warning(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    # IDE-workspace model (skill-workspace alignment §F1/§8, 01_init.md D11 无注册表):
    # Home lists only opened folders, so the skill is opened into the workspace first
    # by recording it in the native-fs skill index — config_mismatch must still surface
    # for an opened folder.
    skills_dir, workspaces_dir = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    local_git = GitLocalService()
    local_git.init(skill_dir)
    local_git.remote_add(
        skill_dir, "origin", "https://gitea.example.test/bob/text-segmentation.git"
    )
    metadata = LocalJsonMetadataStore(
        global_config_dir=config.APP_SETTINGS_DIR,
        workspaces_root=workspaces_dir,
    )
    asyncio.run(
        metadata.save_skill_index_entry(
            "text-segmentation",
            {"absolute_path": str(skill_dir), "l2_remote_url": ""},
        )
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
