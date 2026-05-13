from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from app.services.git_local import (
    GitCommandError,
    GitFileLockedError,
    GitCommandTimeoutError,
    GitLocalService,
    STUDIO_GITIGNORE,
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
            return subprocess.CompletedProcess(command, 128, stdout="", stderr="Unable to create '.git/index.lock'")
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
        return subprocess.CompletedProcess(command, 128, stdout="", stderr="fatal: .git/index.lock exists")

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
    service.commit(tmp_path, "auto-run-1")
    assert service.log(tmp_path) == ["abc auto-run-1"]
    service.reset_hard(tmp_path, "abc")
    service.status(tmp_path, ignored=True)

    assert ["git", "add", "-A"] in commands
    assert ["git", "add", "-f", ".workspace/runs/latest"] in commands
    assert ["git", "commit", "-m", "auto-run-1"] in commands
    assert ["git", "log", "--oneline", "-n50"] in commands
    assert ["git", "reset", "--hard", "abc"] in commands
    assert ["git", "status", "--short", "--ignored"] in commands


def test_auto_commit_respects_gitignore_latest_but_commits_golden_and_predict(
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
    (golden_dir / "golden_metadata.json").write_text("{}", encoding="utf-8")
    predict_dir = skill_dir / ".workspace" / "predict"
    predict_dir.mkdir(parents=True)
    (predict_dir / "latest_predict.json").write_text("{}", encoding="utf-8")

    result = service.auto_commit_run(skill_dir, "run-1")

    assert result is not None
    ignored_status = service.status(skill_dir, ignored=True).stdout
    assert "!! .workspace/runs/" in ignored_status
    committed_files = run_git(skill_dir, "show", "--name-only", "--format=", "HEAD").stdout
    assert ".workspace/golden/run-1/golden_metadata.json" in committed_files
    assert ".workspace/predict/latest_predict.json" in committed_files
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


def test_studio_gitignore_template_is_exact(tmp_path: Path) -> None:
    assert write_studio_gitignore(tmp_path).read_text(encoding="utf-8") == STUDIO_GITIGNORE
