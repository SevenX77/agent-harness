"""Tests for MVP-3 Bootstrap and Settings startup helpers."""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError

import pytest

import graph_agent.bootstrap as bootstrap_module
from graph_agent.bootstrap import Bootstrap
from graph_agent.settings import Settings


def test_apply_patches_calls_central_patch_entry_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_apply_all() -> None:
        calls.append("called")

    monkeypatch.setattr(bootstrap_module.patches, "apply_all", fake_apply_all)

    bootstrap = Bootstrap()
    bootstrap.apply_patches()

    assert calls == ["called"]


def test_apply_patches_twice_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bootstrap_module.patches, "apply_all", lambda: None)
    bootstrap = Bootstrap()

    bootstrap.apply_patches()

    with pytest.raises(RuntimeError, match="called twice"):
        bootstrap.apply_patches()


def test_load_settings_round_trip_from_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    bootstrap = Bootstrap()

    settings = bootstrap.load_settings(
        {
            "OPENAI_API_KEY": "sk-test",
            "GRAPH_AGENT_MODEL_PROVIDER": "openai",
            "GRAPH_AGENT_DEFAULT_ROLE": "fast",
            "GRAPH_AGENT_LOG_LEVEL": "debug",
            "GRAPH_AGENT_DEBUG": "yes",
        }
    )

    assert settings == Settings(
        openai_api_key="sk-test",
        graph_agent_model_provider="openai",
        graph_agent_default_role="fast",
        log_level="DEBUG",
        debug_mode=True,
    )
    assert bootstrap.settings is settings
    assert "OPENAI_API_KEY" not in os.environ


def test_settings_from_env_reads_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
    monkeypatch.setenv("GRAPH_AGENT_PERSONA_PATH", "/tmp/personas")
    monkeypatch.setenv("STUDIO_CHECKPOINTER", "memory")
    monkeypatch.setenv("GRAPH_AGENT_CHECKPOINTER_DB", "/tmp/checkpoints.sqlite")

    settings = Settings.from_env()

    assert settings.anthropic_api_key == "anthropic-key"
    assert settings.graph_agent_persona_path == "/tmp/personas"
    assert settings.studio_checkpointer == "memory"
    assert settings.graph_agent_checkpointer_db == "/tmp/checkpoints.sqlite"


def test_settings_overrides_do_not_mutate_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GRAPH_AGENT_MODEL", raising=False)

    settings = Settings.from_env({"GRAPH_AGENT_MODEL": "gpt-test"})

    assert settings.graph_agent_model == "gpt-test"
    assert "GRAPH_AGENT_MODEL" not in os.environ


def test_settings_invalid_bool_raises() -> None:
    with pytest.raises(ValueError, match="Invalid boolean value"):
        Settings.from_env({"GRAPH_AGENT_DEBUG": "maybe"})


def test_settings_is_frozen() -> None:
    settings = Settings()

    with pytest.raises(FrozenInstanceError):
        settings.log_level = "DEBUG"  # type: ignore[misc]
