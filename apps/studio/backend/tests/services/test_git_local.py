from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from app.services.git_local import (
    STUDIO_GITIGNORE,
    GitCommandError,
    GitCommandTimeoutError,
    GitFileLockedError,
    GitLocalService,
    run_git,
    write_studio_gitignore,
)


def test_run_git_success_captures_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_git(tmp_path, "status", timeout_seconds=3)

    assert result.stdout == "ok\n"
    assert result.returncode == 0
    assert calls[0]["command"] == ["git", "status"]
    assert calls[0]["cwd"] == tmp_path
    assert calls[0]["timeout"] == 3
    assert calls[0]["capture_output"] is True


def test_run_git_nonzero_raises_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        return subprocess.CompletedProcess(command, 128, stdout="", stderr="fatal")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCommandError) as exc_info:
        run_git(tmp_path, "commit", "-m", "x")

    assert exc_info.value.result.returncode == 128
    assert exc_info.value.result.stderr == "fatal"


def test_run_git_timeout_raises_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCommandTimeoutError):
        run_git(tmp_path, "status", timeout_seconds=0.01)


def test_run_git_missing_cwd_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_git(tmp_path / "missing", "status")


def test_run_git_lock_error_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        del kwargs
        calls += 1
        if calls < 3:
            return subprocess.CompletedProcess(
                command, 128, stdout="", stderr="Unable to create '.git/index.lock'"
            )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_git(tmp_path, "commit", "-m", "x", lock_retry_delays=(0, 0))

    assert result.stdout == "ok"
    assert calls == 3


def test_run_git_lock_error_exhaustion_raises_file_locked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        del kwargs
        calls += 1
        return subprocess.CompletedProcess(
            command, 128, stdout="", stderr="fatal: .git/index.lock exists"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitFileLockedError) as exc_info:
        run_git(tmp_path, "add", "-A", lock_retry_delays=(0, 0))

    assert exc_info.value.error_code == "GIT_FILE_LOCKED"
    assert calls == 3


def test_run_git_non_lock_error_does_not_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        del kwargs
        calls += 1
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="nothing to commit")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GitCommandError):
        run_git(tmp_path, "commit", "-m", "x", lock_retry_delays=(0, 0))

    assert calls == 1


def test_git_service_wrappers_build_expected_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        commands.append(command)
        stdout = "M SKILL.md\n" if command[1:3] == ["status", "--short"] else ""
        if command[1] == "log":
            stdout = "abc auto-run-1\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = GitLocalService(timeout_seconds=5)

    service.add(tmp_path)
    service.add(tmp_path, ".workspace/runs/latest", force=True)
    service.force_add_path(tmp_path, ".workspace/runs/latest")
    service.create_branch(tmp_path, "team-save/tester-1")
    service.commit(tmp_path, "auto-run-1")
    assert service.log(tmp_path) == ["abc auto-run-1"]
    service.reset_hard(tmp_path, "abc")
    service.status(tmp_path, ignored=True)

    assert ["git", "add", "-A"] in commands
    assert ["git", "add", "-f", ".workspace/runs/latest"] in commands
    assert ["git", "checkout", "-b", "team-save/tester-1"] in commands
    assert ["git", "commit", "-m", "auto-run-1"] in commands
    assert ["git", "log", "--oneline", "-n50"] in commands
    assert ["git", "reset", "--hard", "abc"] in commands
    assert ["git", "status", "--short", "--ignored"] in commands


def test_auto_commit_respects_gitignore_latest_but_commits_golden(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    write_studio_gitignore(skill_dir)
    service = GitLocalService()
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")

    latest_dir = skill_dir / ".workspace" / "runs" / "latest"
    latest_dir.mkdir(parents=True)
    (latest_dir / "run_metadata.json").write_text("{}", encoding="utf-8")
    golden_dir = skill_dir / ".workspace" / "golden" / "run-1"
    golden_dir.mkdir(parents=True)
    (golden_dir / "baseline.json").write_text("{}", encoding="utf-8")
    (golden_dir / "report.json").write_text("{}", encoding="utf-8")
    (golden_dir / "cases").mkdir()
    (golden_dir / "cases" / "setup.json").write_text("{}", encoding="utf-8")

    result = service.auto_commit_run(skill_dir, "run-1")

    assert result is not None
    ignored_status = service.status(skill_dir, ignored=True).stdout
    assert "!! .workspace/runs/" in ignored_status
    committed_files = run_git(skill_dir, "show", "--name-only", "--format=", "HEAD").stdout
    assert ".workspace/golden/run-1/baseline.json" in committed_files
    assert ".workspace/golden/run-1/report.json" in committed_files
    assert ".workspace/golden/run-1/cases/setup.json" in committed_files
    assert ".workspace/predict/" not in committed_files
    assert ".workspace/runs/latest" not in committed_files


def test_force_add_path_overrides_gitignore(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    service = GitLocalService()
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    (skill_dir / ".gitignore").write_text("/.workspace/*\n", encoding="utf-8")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")

    latest_dir = skill_dir / ".workspace" / "runs" / "latest"
    latest_dir.mkdir(parents=True)
    (latest_dir / "x.json").write_text("data\n", encoding="utf-8")

    service.add(skill_dir)
    assert ".workspace/runs/latest/x.json" not in service.status(skill_dir).stdout

    service.force_add_path(skill_dir, ".workspace/runs/latest")

    assert "A  .workspace/runs/latest/x.json" in service.status(skill_dir).stdout


def test_create_branch_checks_out_new_branch(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    service = GitLocalService()
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")

    service.create_branch(skill_dir, "team-save/tester-1")

    assert run_git(skill_dir, "branch", "--show-current").stdout.strip() == "team-save/tester-1"


def test_commit_empty_snapshot_retries_cas_when_head_advances(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    service = GitLocalService(lock_retry_delays=())
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")
    original_run = subprocess.run
    advanced_head = False

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        nonlocal advanced_head
        if command[0:3] == ["git", "update-ref", "HEAD"] and not advanced_head:
            advanced_head = True
            original_run(
                ["git", "commit", "--allow-empty", "-m", "manual-concurrent"],
                cwd=kwargs["cwd"],
                timeout=kwargs.get("timeout"),
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    service.commit_empty_snapshot(skill_dir, "release-1.0.0")

    subjects = run_git(skill_dir, "log", "--format=%s").stdout.splitlines()
    assert subjects.count("release-1.0.0") == 1
    assert "manual-concurrent" in subjects


def test_commit_empty_snapshot_does_not_reuse_non_empty_commit_with_same_subject(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    service = GitLocalService(lock_retry_delays=())
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")
    (skill_dir / "RELEASE_NOTES.md").write_text("user authored release notes\n", encoding="utf-8")
    service.add(skill_dir)
    service.commit(skill_dir, "release-1.0.0")
    ordinary_sha = run_git(skill_dir, "rev-parse", "HEAD").stdout.strip()

    marker_sha = service.commit_empty_snapshot(skill_dir, "release-1.0.0")

    subjects = run_git(skill_dir, "log", "--format=%s").stdout.splitlines()
    marker_changed_files = run_git(
        skill_dir,
        "diff-tree",
        "--no-commit-id",
        "--name-only",
        "-r",
        "--root",
        marker_sha,
    ).stdout.splitlines()
    assert marker_sha != ordinary_sha
    assert subjects.count("release-1.0.0") == 2
    assert marker_changed_files == []


def test_commit_empty_snapshot_uses_concurrent_existing_marker_after_cas_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    service = GitLocalService(lock_retry_delays=())
    service.init(skill_dir)
    run_git(skill_dir, "config", "--local", "user.name", "tester")
    run_git(skill_dir, "config", "--local", "user.email", "tester@studio.local")
    service.add(skill_dir)
    service.commit(skill_dir, "initial")
    original_run = subprocess.run
    concurrent_marker: dict[str, str] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0:3] == ["git", "update-ref", "HEAD"] and not concurrent_marker:
            result = original_run(
                ["git", "commit", "--allow-empty", "-m", "release-1.0.0"],
                cwd=kwargs["cwd"],
                timeout=kwargs.get("timeout"),
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            assert result.returncode == 0, result.stderr
            sha_result = original_run(
                ["git", "rev-parse", "HEAD"],
                cwd=kwargs["cwd"],
                timeout=kwargs.get("timeout"),
                capture_output=True,
                text=True, encoding="utf-8", errors="replace",
            )
            concurrent_marker["sha"] = sha_result.stdout.strip()
        return original_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    marker_sha = service.commit_empty_snapshot(skill_dir, "release-1.0.0")

    subjects = run_git(skill_dir, "log", "--format=%s").stdout.splitlines()
    assert subjects.count("release-1.0.0") == 1
    assert marker_sha == concurrent_marker["sha"]


def test_studio_gitignore_template_is_exact(tmp_path: Path) -> None:
    assert write_studio_gitignore(tmp_path).read_text(encoding="utf-8") == STUDIO_GITIGNORE
