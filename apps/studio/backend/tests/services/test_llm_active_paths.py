from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from app.core import config
from app.services import llm_credentials, llm_import_drafts, llm_roles


def _load_path_helpers():
    try:
        return importlib.import_module("app.services.llm_paths")
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing Studio LLM path helper module: {exc}")


def test_active_llm_paths_default_to_app_settings_llm_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_ROLES_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_IMPORT_DRAFTS_PATH", raising=False)
    monkeypatch.delenv("STUDIO_LLM_CANONICAL_RULES_PATH", raising=False)

    llm_paths = _load_path_helpers()

    assert llm_credentials.credentials_path() == settings_dir / "llm" / "llm_credentials.json"
    assert llm_roles.roles_path() == settings_dir / "llm" / "llm_roles.yaml"
    assert llm_import_drafts.drafts_path() == settings_dir / "llm" / "llm_import_drafts.json"
    assert llm_paths.canonical_rules_path() == settings_dir / "llm" / "llm_canonical_rules.yaml"


def test_active_llm_paths_support_explicit_env_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path / "settings")
    credentials_override = tmp_path / "custom" / "credentials.json"
    roles_override = tmp_path / "custom" / "roles.yaml"
    drafts_override = tmp_path / "custom" / "drafts.json"
    canonical_override = tmp_path / "custom" / "canonical.yaml"
    monkeypatch.setenv("STUDIO_LLM_CREDENTIALS_PATH", str(credentials_override))
    monkeypatch.setenv("STUDIO_LLM_ROLES_PATH", str(roles_override))
    monkeypatch.setenv("STUDIO_LLM_IMPORT_DRAFTS_PATH", str(drafts_override))
    monkeypatch.setenv("STUDIO_LLM_CANONICAL_RULES_PATH", str(canonical_override))

    llm_paths = _load_path_helpers()

    assert llm_credentials.credentials_path() == credentials_override
    assert llm_roles.roles_path() == roles_override
    assert llm_import_drafts.drafts_path() == drafts_override
    assert llm_paths.canonical_rules_path() == canonical_override
