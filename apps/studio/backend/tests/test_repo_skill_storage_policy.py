from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_repo_root_does_not_track_runtime_skills_directory() -> None:
    """Studio runtime skills live outside this repo as one git repo per skill."""
    result = subprocess.run(
        ["git", "ls-files", "--", "skills"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    assert result.stdout == ""
