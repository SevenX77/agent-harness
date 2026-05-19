from __future__ import annotations

from pathlib import Path

from app.models.settings import AppSettings
from app.services.config_arbitration import detect_config_mismatch
from app.services.git_local import GitLocalService


def test_no_warning_when_gitea_host_empty(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = GitLocalService()
    local_git.remote_add(skill_dir, "origin", "https://gitea.example.test/alice/demo.git")

    warning = detect_config_mismatch(
        "demo",
        skill_dir,
        AppSettings(user_id="alice", gitea_host=""),
        local_git=local_git,
    )

    assert warning is None


def test_no_warning_when_user_id_empty(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = GitLocalService()
    local_git.remote_add(skill_dir, "origin", "https://gitea.example.test/alice/demo.git")

    warning = detect_config_mismatch(
        "demo",
        skill_dir,
        AppSettings(user_id="", gitea_host="https://gitea.example.test"),
        local_git=local_git,
    )

    assert warning is None


def test_no_warning_when_skill_has_no_origin(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)

    warning = detect_config_mismatch(
        "demo",
        skill_dir,
        AppSettings(user_id="alice", gitea_host="https://gitea.example.test"),
        local_git=GitLocalService(),
    )

    assert warning is None


def test_no_warning_when_urls_match(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = GitLocalService()
    local_git.remote_add(skill_dir, "origin", "https://gitea.example.test/alice/demo.git")

    warning = detect_config_mismatch(
        "demo",
        skill_dir,
        AppSettings(user_id="alice", gitea_host="https://gitea.example.test"),
        local_git=local_git,
    )

    assert warning is None


def test_warning_when_urls_differ(tmp_path: Path) -> None:
    skill_dir = _init_repo(tmp_path)
    local_git = GitLocalService()
    local_git.remote_add(skill_dir, "origin", "https://gitea.example.test/bob/demo.git")

    warning = detect_config_mismatch(
        "demo",
        skill_dir,
        AppSettings(user_id="alice", gitea_host="https://gitea.example.test/"),
        local_git=local_git,
    )

    assert warning is not None
    assert warning.actual_remote_url == "https://gitea.example.test/bob/demo.git"
    assert warning.expected_remote_url == "https://gitea.example.test/alice/demo.git"
    assert (
        warning.recommendation
        == "建议以 .git/config 为基准 (per design.md 决策 22), 在 Settings 调整 User ID / Gitea Host"
    )


def _init_repo(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    GitLocalService().init(skill_dir)
    return skill_dir
