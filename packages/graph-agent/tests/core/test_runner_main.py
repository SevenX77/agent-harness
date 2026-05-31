from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

from graph_agent.core import runner
from graph_agent.core.exceptions import LoaderError


def _write_skill(tmp_path: Path) -> Path:
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("# test skill\n", encoding="utf-8")
    return skill_path


def test_main_dotenv_import_failure_raises_loader_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skill_path = _write_skill(tmp_path)
    original_import = builtins.__import__

    def _blocked_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "dotenv":
            raise ImportError("dotenv missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    monkeypatch.setattr(sys, "argv", ["graph-agent", "--skill", str(skill_path)])

    with pytest.raises(LoaderError) as exc_info:
        runner.main()

    assert "required import failed: dotenv missing" in str(exc_info.value)
    assert exc_info.value.context == {"module": "dotenv"}
    assert isinstance(exc_info.value.__cause__, ImportError)
