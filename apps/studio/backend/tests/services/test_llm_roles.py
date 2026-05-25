from __future__ import annotations

import os
from pathlib import Path
from textwrap import dedent

import pytest
from app.models.llm_config import RoleEntry
from app.routers import llm as llm_router
from app.services.llm_roles import (
    InvalidRoleReference,
    get_role,
    load_roles_file,
    save_roles_file,
    validate_references,
)
from fastapi.testclient import TestClient

SAMPLE_ROLES_YAML = dedent(
    """
    models:
      CL46T:
        name: Claude Sonnet 4.6 Thinking
        reasoning: true
        providers:
          OC_CL_ANT: claude-sonnet-4-6-thinking
          WS_LLM: anthropic/claude-sonnet-4.6
      CLO46T:
        name: Claude Opus 4.6 Thinking
        reasoning: true
        providers:
          OC_CL_ANT: claude-opus-4-6-thinking
          WS_LLM: anthropic/claude-opus-4.6
      CLO47T:
        name: Claude Opus 4.7 Thinking
        reasoning: true
        providers:
          OC_CL_ANT: claude-opus-4-7
          WS_LLM: anthropic/claude-opus-4.7
      DS32R:
        name: DeepSeek-V4 Pro
        reasoning: true
        providers:
          DS: deepseek-v4-pro
          OC_DS: deepseek/deepseek-r1-0528
    providers:
      OC_CL_ANT:
        name: OneChats Claude (Anthropic Endpoint)
        type: anthropic_compatible
      WS_LLM:
        name: WaveSpeed Any-LLM
        type: openai_compatible
      DS:
        name: DeepSeek Official
        type: openai_compatible
      OC_DS:
        name: OneChats DeepSeek
        type: openai_compatible
    roles:
      balanced:
        model_fallback: false
        active_model: CL46T
        temperature: 0.7
        models:
          CL46T:
            providers:
            - OC_CL_ANT
            - WS_LLM
          DS32R:
            providers:
            - DS
            - OC_DS
      premium:
        model_fallback: true
        active_model: CLO47T
        temperature: 0.7
        models:
          CLO47T:
            providers:
            - OC_CL_ANT
            - WS_LLM
          CLO46T:
            providers:
            - OC_CL_ANT
            - WS_LLM
          CL46T:
            providers:
            - OC_CL_ANT
            - WS_LLM
    single_model_roles: []
    peer_model_groups: {}
    """
).lstrip()


def test_load_roles_yaml_save_migrates_once_then_stays_stable(tmp_path: Path) -> None:
    path = _copy_roles_yaml(tmp_path)
    before = path.read_text(encoding="utf-8")

    data = load_roles_file(path)
    save_roles_file(path, data)
    migrated = path.read_text(encoding="utf-8")

    assert migrated != before
    assert "temperature" not in load_roles_file(path).roles["balanced"].model_fields_set

    data = load_roles_file(path)
    save_roles_file(path, data)

    assert path.read_text(encoding="utf-8") == migrated


def test_load_get_role_returns_active_model(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))

    assert get_role(data, "balanced").active_model == "CL46T"


def test_load_roles_yaml_migrates_role_temperature_to_model_entries(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))
    role = get_role(data, "balanced")

    assert not hasattr(role, "temperature")
    assert role.models["CL46T"].temperature == 0.7
    assert role.models["DS32R"].temperature == 0.7


def test_load_get_role_fallback_order(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))

    assert list(get_role(data, "premium").models) == ["CLO47T", "CLO46T", "CL46T"]


def test_validate_references_passes_on_valid_yaml(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))

    validate_references(data)


def test_validate_references_allows_empty_draft_role(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))
    data.roles["draft_role"] = RoleEntry(model_fallback=True, active_model="", models={})

    validate_references(data)


def test_validate_references_fails_on_missing_model(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))
    data.roles["balanced"].active_model = "MISSING_MODEL"

    with pytest.raises(InvalidRoleReference) as exc_info:
        validate_references(data)

    assert "balanced" in str(exc_info.value)
    assert "MISSING_MODEL" in str(exc_info.value)


def test_validate_references_fails_on_missing_provider(tmp_path: Path) -> None:
    data = load_roles_file(_copy_roles_yaml(tmp_path))
    data.roles["balanced"].models["CL46T"].providers = ["MISSING_PROVIDER"]

    with pytest.raises(InvalidRoleReference) as exc_info:
        validate_references(data)

    assert "balanced" in str(exc_info.value)
    assert "MISSING_PROVIDER" in str(exc_info.value)


def test_save_atomic_write_does_not_leave_partial_file_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_roles_yaml(tmp_path)
    before = path.read_text(encoding="utf-8")
    data = load_roles_file(path)
    data.roles["balanced"].active_model = "DS32R"

    def fail_replace(_src: Path, _dst: Path) -> None:
        raise OSError("rename failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        save_roles_file(path, data)

    assert path.read_text(encoding="utf-8") == before
    assert not list(path.parent.glob("*.tmp"))


def test_round_trip_via_api_get_put_get(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_roles_yaml(tmp_path)
    monkeypatch.setattr(llm_router, "ROLES_PATH", path)

    get_response = client.get("/api/llm/roles/balanced")
    payload = client.get("/api/llm/roles").json()
    payload["roles"]["balanced"]["active_model"] = "DS32R"

    put_response = client.put("/api/llm/roles", json=payload)
    second_get = client.get("/api/llm/roles/balanced")

    assert get_response.status_code == 200
    assert get_response.json()["active_model"] == "CL46T"
    assert put_response.status_code == 200
    assert second_get.json()["active_model"] == "DS32R"
    assert load_roles_file(path).roles["balanced"].active_model == "DS32R"


def test_api_put_roles_normalizes_empty_draft_active_model(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_roles_yaml(tmp_path)
    monkeypatch.setattr(llm_router, "ROLES_PATH", path)

    payload = client.get("/api/llm/roles").json()
    payload["roles"]["draft_role"] = {
        "model_fallback": True,
        "active_model": "unknown model",
        "models": {},
    }

    put_response = client.put("/api/llm/roles", json=payload)

    assert put_response.status_code == 200
    assert put_response.json()["roles"]["draft_role"]["active_model"] == ""
    assert load_roles_file(path).roles["draft_role"].active_model == ""


def test_api_put_roles_normalizes_stale_draft_model(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _copy_roles_yaml(tmp_path)
    monkeypatch.setattr(llm_router, "ROLES_PATH", path)

    payload = client.get("/api/llm/roles").json()
    payload["roles"]["test"] = {
        "model_fallback": True,
        "active_model": "unknown model",
        "models": {
            "unknown model": {"providers": []},
        },
    }

    put_response = client.put("/api/llm/roles", json=payload)

    assert put_response.status_code == 200
    assert put_response.json()["roles"]["test"]["active_model"] == ""
    assert put_response.json()["roles"]["test"]["models"] == {}
    saved_role = load_roles_file(path).roles["test"]
    assert saved_role.active_model == ""
    assert saved_role.models == {}


def _copy_roles_yaml(tmp_path: Path) -> Path:
    target = tmp_path / "llm_roles.yaml"
    target.write_text(SAMPLE_ROLES_YAML, encoding="utf-8")
    return target
