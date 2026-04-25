"""Unit tests for the persona registry."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graph_agent.core.personas import (
    PERSONA_PATH_ENV_VAR,
    default_persona_search_paths,
)


def test_default_search_paths_empty_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PERSONA_PATH_ENV_VAR, raising=False)
    assert default_persona_search_paths() == []


def test_default_search_paths_returns_env_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, f"{a}{os.pathsep}{b}")
    assert default_persona_search_paths() == [a, b]


def test_default_search_paths_skips_empty_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    a.mkdir()
    # leading separator + double separator + trailing separator should all be ignored
    monkeypatch.setenv(PERSONA_PATH_ENV_VAR, f"{os.pathsep}{a}{os.pathsep}{os.pathsep}")
    assert default_persona_search_paths() == [a]
