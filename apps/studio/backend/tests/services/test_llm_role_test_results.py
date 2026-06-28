"""R20: durable role/copilot test-result store survives a simulated restart."""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core import config
from app.services import llm_role_test_results
from app.services.llm_role_test_results import (
    load_all,
    load_result,
    results_path,
    save_result,
)


def _role_test_response(role_name: str) -> dict[str, object]:
    return {
        "role_name": role_name,
        "status": "ok",
        "warnings": [],
        "model_groups": [
            {
                "canonical_id": "claude-opus-4-7",
                "display_name": "Claude Opus 4.7",
                "provider_results": [
                    {
                        "route_id": "anthropic-official:claude-opus-4-7",
                        "status": "ok",
                    }
                ],
            }
        ],
    }


def test_save_then_load_result_roundtrips(tmp_path: Path) -> None:
    store = tmp_path / "llm_role_test_results.json"
    result = _role_test_response("analyst")

    save_result("analyst", result, status="ok", message="Role test completed.", path=store)

    loaded = load_result("analyst", path=store)
    assert loaded is not None
    assert loaded["role_name"] == "analyst"
    assert loaded["status"] == "ok"
    assert loaded["message"] == "Role test completed."
    assert loaded["result"] == result
    assert "updated_at" in loaded


def test_completed_result_survives_store_reconstruction(tmp_path: Path) -> None:
    """A completed result must be readable after the process is gone.

    The store keeps no in-memory state — every read hits disk — so reading from
    a fresh path-bound call after the write is exactly the restart scenario:
    nothing in this run carries the value over except the file itself.
    """
    store = tmp_path / "llm_role_test_results.json"
    save_result(
        "copilot_opus_4_7",
        {"role_name": "copilot_opus_4_7", "status": "ok", "model_groups": []},
        status="ok",
        path=store,
    )

    # Simulate restart: read everything fresh from the persisted file only.
    reconstructed = load_all(path=store)
    assert "copilot_opus_4_7" in reconstructed
    assert reconstructed["copilot_opus_4_7"]["status"] == "ok"


def test_save_keeps_results_for_other_roles(tmp_path: Path) -> None:
    store = tmp_path / "llm_role_test_results.json"
    save_result("analyst", _role_test_response("analyst"), status="ok", path=store)
    save_result(
        "copilot_chat",
        {"role_name": "copilot_chat", "status": "failed", "model_groups": []},
        status="failed",
        path=store,
    )

    all_results = load_all(path=store)
    assert set(all_results) == {"analyst", "copilot_chat"}
    assert all_results["analyst"]["status"] == "ok"
    assert all_results["copilot_chat"]["status"] == "failed"


def test_save_overwrites_last_result_for_same_role(tmp_path: Path) -> None:
    store = tmp_path / "llm_role_test_results.json"
    save_result("analyst", {"status": "failed", "model_groups": []}, status="failed", path=store)
    save_result("analyst", {"status": "ok", "model_groups": []}, status="ok", path=store)

    loaded = load_result("analyst", path=store)
    assert loaded is not None
    assert loaded["status"] == "ok"


def test_load_all_is_empty_when_store_absent(tmp_path: Path) -> None:
    assert load_all(path=tmp_path / "missing.json") == {}


def test_results_path_defaults_to_llm_settings_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    monkeypatch.delenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", raising=False)

    assert results_path() == settings_dir / "llm" / "llm_role_test_results.json"


def test_results_path_supports_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    override = tmp_path / "custom" / "results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(override))

    assert results_path() == override


def test_default_path_write_uses_results_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """save_result with no explicit path writes to the active results_path()."""
    override = tmp_path / "active" / "llm_role_test_results.json"
    monkeypatch.setenv("STUDIO_LLM_ROLE_TEST_RESULTS_PATH", str(override))

    save_result("analyst", {"status": "ok", "model_groups": []}, status="ok")

    assert override.exists()
    assert llm_role_test_results.load_result("analyst") is not None
