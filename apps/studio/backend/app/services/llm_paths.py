"""Active Studio LLM runtime config paths."""

from __future__ import annotations

import os
from pathlib import Path

from app.core import config

_LLM_SETTINGS_DIR = "llm"


def credentials_path() -> Path:
    """Return the active Studio LLM credentials path."""
    return _env_or_default(
        "STUDIO_LLM_CREDENTIALS_PATH",
        "llm_credentials.json",
    )


def roles_path() -> Path:
    """Return the active Studio LLM roles path."""
    return _env_or_default(
        "STUDIO_LLM_ROLES_PATH",
        "llm_roles.yaml",
    )


def import_drafts_path() -> Path:
    """Return the legacy import-drafts path alias for the probe catalog."""
    return probe_catalog_path()


def probe_catalog_path() -> Path:
    """Return the active Studio LLM probe knowledge catalog path."""
    override = os.environ.get("STUDIO_LLM_PROBE_CATALOG_PATH") or os.environ.get(
        "STUDIO_LLM_IMPORT_DRAFTS_PATH"
    )
    if override:
        return Path(override).expanduser()
    return config.APP_SETTINGS_DIR / _LLM_SETTINGS_DIR / "llm_probe_catalog.json"


def role_test_results_path() -> Path:
    """Return the active Studio LLM role/copilot test-result store path."""
    return _env_or_default(
        "STUDIO_LLM_ROLE_TEST_RESULTS_PATH",
        "llm_role_test_results.json",
    )


def canonical_rules_path() -> Path:
    """Return the active Studio LLM canonical rules path."""
    return _env_or_default(
        "STUDIO_LLM_CANONICAL_RULES_PATH",
        "llm_canonical_rules.yaml",
    )


def _env_or_default(env_name: str, filename: str) -> Path:
    override = os.environ.get(env_name)
    if override:
        return Path(override).expanduser()
    return config.APP_SETTINGS_DIR / _LLM_SETTINGS_DIR / filename


__all__ = [
    "canonical_rules_path",
    "credentials_path",
    "import_drafts_path",
    "probe_catalog_path",
    "role_test_results_path",
    "roles_path",
]
