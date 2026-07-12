"""Tasks 2.5/2.6 — predict_skill MCP tool and the LLM role config write tools.

predict_skill rides the existing backend predict exit (PredictorService) and
compacts the result; the role write tools go through the SAME service chain as
PUT /api/llm/roles (validate → materialize → save → domain event) and return a
plain success status (the before/after undo snapshot is deleted — writes hold
for approval instead). Credentials/endpoints have dedicated write tools.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from app.services import copilot_tools


def _payload(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(result["content"][0]["text"])


# ── predict_skill (2.5) ─────────────────────────────────────────────────────


def test_predict_skill_tool_requires_skill_id() -> None:
    result = asyncio.run(copilot_tools.predict_skill_tool.handler({"skill_id": " "}))
    assert result["is_error"] is True
    assert "skill_id" in result["content"][0]["text"]


def test_predict_skill_tool_compacts_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.runs import PredictDiagnosticExport
    from app.services import predictor

    class _FakeResult:
        run_id = "run-123"
        success = True

    export = PredictDiagnosticExport.model_validate(
        {
            "is_predict": True,
            "status": "success",
            "phases": [
                {
                    "phase_name": "extract",
                    "type": "llm",
                    "inputs": {"big": "x" * 500},
                    "outputs": {"big": "y" * 500},
                    "mocked_source": "heuristic_stub",
                }
            ],
            "path_diff": {
                "expected_path": ["extract"],
                "actual_path": ["extract"],
            },
            "diagnostics": [],
            "diagnostics_truncated": False,
            "diagnostic_counts": {"error": 0},
        }
    )
    monkeypatch.setattr(
        predictor.predictor_service, "dispatch_predict_job", lambda skill_id: _FakeResult()
    )
    monkeypatch.setattr(
        predictor.predictor_service, "export_diagnostics", lambda result: export
    )

    result = asyncio.run(copilot_tools.predict_skill_tool.handler({"skill_id": "s1"}))

    assert "is_error" not in result
    payload = _payload(result)
    assert payload["success"] is True
    assert payload["run_id"] == "run-123"
    # phases compacted: no inputs/outputs dumps into model context
    assert payload["phases"] == [
        {"phase_name": "extract", "type": "llm", "mocked_source": "heuristic_stub"}
    ]
    assert payload["path_diff"]["actual_path"] == ["extract"]
    assert payload["diagnostic_counts"] == {"error": 0}
    assert ".workspace/runs/run-123" in payload["detail_hint"]


def test_predict_skill_tool_reports_failure_structurally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import predictor

    def _boom(skill_id: str) -> Any:
        raise predictor.PredictArtifactError("engine.bad", {"message": "broken graph"})

    monkeypatch.setattr(predictor.predictor_service, "dispatch_predict_job", _boom)

    result = asyncio.run(copilot_tools.predict_skill_tool.handler({"skill_id": "s1"}))

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "engine.bad" in text or "broken graph" in text


# ── create_llm_role / update_llm_role (2.6) ─────────────────────────────────


def _fake_roles_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the routers.llm service chain; capture what got saved/published."""

    from app.models.llm_config import LLMCredentialsFile, ProviderRoute, RolesData
    from app.routers import llm
    from app.services import llm_credentials, runtime_activity

    state: dict[str, Any] = {"saved": None, "published": 0, "data": RolesData()}

    # The vocab guard now looks the route up in credentials and compares its DERIVED
    # canonical_id, so the stubbed credentials must carry the route the groups cite.
    credentials = LLMCredentialsFile(
        provider_routes={
            "prov-x:gpt-5": ProviderRoute(
                route_id="prov-x:gpt-5",
                endpoint_id="prov-x",
                route_slug="gpt-5",
                provider_model_id="gpt-5",
            )
        }
    )
    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: state["data"])
    monkeypatch.setattr(llm_credentials, "load_credentials", lambda: credentials)
    monkeypatch.setattr(
        llm, "_materialize_roles_for_response", lambda data, credentials=None: data
    )

    def _save(data: Any) -> Any:
        state["saved"] = data
        return data

    monkeypatch.setattr(llm, "_save_roles_with_active_routes", _save)

    async def _publish() -> None:
        state["published"] += 1

    monkeypatch.setattr(llm, "_publish_roles_changed", _publish)
    monkeypatch.setattr(
        runtime_activity, "record_runtime_activity", lambda **kwargs: None
    )
    return state


_GROUPS = [
    {
        "canonical_id": "gpt-5",
        "display_name": "GPT-5",
        "provider_models": [{"route_id": "prov-x:gpt-5"}],
    }
]


def test_create_llm_role_saves_via_service_chain_and_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _fake_roles_env(monkeypatch)

    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {"name": "writer", "model_groups": _GROUPS}
        )
    )

    assert "is_error" not in result, result
    payload = _payload(result)
    assert payload["role_name"] == "writer"
    assert payload["status"] == "success"
    # Undo snapshot deleted: no before/after in the response.
    assert "before" not in payload
    assert "after" not in payload
    assert state["saved"] is not None and "writer" in state["saved"].roles
    assert state["published"] == 1


def test_create_llm_role_rejects_existing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.llm_config import RoleEntry

    state = _fake_roles_env(monkeypatch)
    state["data"].roles["writer"] = RoleEntry()

    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {"name": "writer", "model_groups": _GROUPS}
        )
    )

    assert result["is_error"] is True
    assert "writer" in result["content"][0]["text"]
    assert state["saved"] is None


def test_update_llm_role_returns_success_and_applies_ops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.llm_config import RoleEntry, RoleModelGroup, RoleProviderModel

    state = _fake_roles_env(monkeypatch)
    state["data"].roles["writer"] = RoleEntry(
        model_groups=[
            RoleModelGroup(
                canonical_id="old/model",
                display_name="Old",
                provider_models=[RoleProviderModel(route_id="prov-x:old/model")],
            )
        ]
    )

    result = asyncio.run(
        copilot_tools.update_llm_role_tool.handler(
            {
                "role_name": "writer",
                "ops": {
                    "set_model_groups": _GROUPS,
                    "model_fallback_enabled": False,
                    "intent": {"thinking": True},
                },
            }
        )
    )

    assert "is_error" not in result, result
    payload = _payload(result)
    assert payload["status"] == "success"
    assert payload["role_name"] == "writer"
    # Undo snapshot deleted: the ops still applied through the service chain.
    assert "before" not in payload
    assert "after" not in payload
    saved_role = state["saved"].roles["writer"]
    assert saved_role.model_fallback_enabled is False
    assert saved_role.model_groups[0].canonical_id == "gpt-5"
    assert saved_role.intent.thinking is True
    assert state["published"] == 1


def test_update_llm_role_rejects_unknown_role(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _fake_roles_env(monkeypatch)

    result = asyncio.run(
        copilot_tools.update_llm_role_tool.handler({"role_name": "ghost", "ops": {}})
    )

    assert result["is_error"] is True
    assert "ghost" in result["content"][0]["text"]
    assert state["saved"] is None


def test_role_write_tools_expose_no_credential_or_endpoint_surface() -> None:
    # R10.3: no credential/endpoint write path through the tool schemas
    for t in (copilot_tools.create_llm_role_tool, copilot_tools.update_llm_role_tool):
        schema_text = str(getattr(t, "input_schema", {}))
        assert "credential" not in schema_text
        assert "api_key" not in schema_text
        assert "endpoint" not in schema_text
