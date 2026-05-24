"""
Test: test_role_migration.py
Covers: design.md §2.1 (LLM Roles Phase 1 data migration) +
tasks.md α5 (load-time in-memory migration and save path) +
requirements.md §3 R[NEW]-Roles-01.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "apps" / "studio" / "backend"
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))


def _legacy_roles_yaml() -> str:
    return """
models:
  GPT5:
    name: GPT-5
    reasoning: false
    providers:
      openai: gpt-5
providers:
  openai:
    name: OpenAI
    type: openai_compatible
roles:
  balanced:
    temperature: 0.4
    max_tokens: 2048
    model_fallback: false
    active_model: GPT5
    models:
      GPT5:
        providers:
          - openai
single_model_roles: []
peer_model_groups: {}
""".lstrip()


def _legacy_roles_yaml_without_max_tokens() -> str:
    return _legacy_roles_yaml().replace("    max_tokens: 2048\n", "")


def test_load_roles_file_migrates_temperature_and_max_tokens_in_memory(
    tmp_path: Path,
) -> None:
    from app.services.llm_roles import load_roles_file

    path = tmp_path / "llm_roles.yaml"
    original = _legacy_roles_yaml()
    path.write_text(original, encoding="utf-8")

    data = load_roles_file(path)
    role = data.roles["balanced"]

    assert not hasattr(role, "temperature")
    assert not hasattr(role, "max_tokens")
    assert role.models["GPT5"].temperature == 0.4
    assert role.models["GPT5"].max_tokens == 2048
    assert path.read_text(encoding="utf-8") == original


def test_save_roles_file_persists_migrated_model_level_parameters(
    tmp_path: Path,
) -> None:
    from app.services.llm_roles import load_roles_file, save_roles_file

    path = tmp_path / "llm_roles.yaml"
    path.write_text(_legacy_roles_yaml(), encoding="utf-8")

    data = load_roles_file(path)
    save_roles_file(path, data)
    saved = path.read_text(encoding="utf-8")

    assert "temperature: 0.4" in saved
    assert "max_tokens: 2048" in saved
    assert "roles:\n  balanced:\n    temperature" not in saved
    assert "roles:\n  balanced:\n    max_tokens" not in saved


def test_put_roles_save_path_round_trips_migrated_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("STUDIO_API_TOKEN", "test-token")
    from app.main import app
    from app.routers import llm as llm_router

    path = tmp_path / "llm_roles.yaml"
    path.write_text(_legacy_roles_yaml(), encoding="utf-8")
    monkeypatch.setattr(llm_router, "ROLES_PATH", path)
    client = TestClient(app)

    headers = {"Authorization": "Bearer test-token"}
    payload = client.get("/api/llm/roles", headers=headers).json()

    assert "temperature" not in payload["roles"]["balanced"]
    assert "max_tokens" not in payload["roles"]["balanced"]
    assert payload["roles"]["balanced"]["models"]["GPT5"]["temperature"] == 0.4
    assert payload["roles"]["balanced"]["models"]["GPT5"]["max_tokens"] == 2048
    assert path.read_text(encoding="utf-8") == _legacy_roles_yaml()

    response = client.put("/api/llm/roles", json=payload, headers=headers)

    assert response.status_code == 200
    assert "temperature: 0.4" in path.read_text(encoding="utf-8")
    assert "max_tokens: 2048" in path.read_text(encoding="utf-8")


def test_legacy_roles_without_max_tokens_keeps_model_max_tokens_none(
    tmp_path: Path,
) -> None:
    from app.services.llm_roles import load_roles_file

    path = tmp_path / "llm_roles.yaml"
    path.write_text(_legacy_roles_yaml_without_max_tokens(), encoding="utf-8")

    data = load_roles_file(path)

    assert data.roles["balanced"].models["GPT5"].temperature == 0.4
    assert data.roles["balanced"].models["GPT5"].max_tokens is None
    assert path.read_text(encoding="utf-8") == _legacy_roles_yaml_without_max_tokens()
