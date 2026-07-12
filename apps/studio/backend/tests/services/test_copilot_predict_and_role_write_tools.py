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


# Read/write symmetry: the write tools accept a FLAT route list (str route_id, or a
# dict carrying route_id + derived runtime_settings the server strips). The server
# auto-groups by each route's DERIVED canonical_id — the client never sends one.
_FLAT_CHAIN = ["prov-x:gpt-5"]


def test_create_llm_role_saves_via_service_chain_and_returns_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _fake_roles_env(monkeypatch)

    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {"name": "writer", "fallback_chain": _FLAT_CHAIN}
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
    saved_role = state["saved"].roles["writer"]
    assert saved_role.model_groups[0].canonical_id == "gpt-5"
    assert saved_role.model_groups[0].provider_models[0].route_id == "prov-x:gpt-5"
    assert state["published"] == 1


def test_create_llm_role_rejects_existing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.models.llm_config import RoleEntry

    state = _fake_roles_env(monkeypatch)
    state["data"].roles["writer"] = RoleEntry()

    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {"name": "writer", "fallback_chain": _FLAT_CHAIN}
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
                    "set_fallback_chain": _FLAT_CHAIN,
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


# ── flat route input: server auto-groups by derived canonical (Requirement 12) ──


def _credentials_multi(*specs: tuple[str, str, str | None]) -> Any:
    """LLMCredentialsFile covering (route_id, provider_model_id, display_name) triples;
    canonical_id is derived, never passed."""
    from app.models.llm_config import LLMCredentialsFile, ProviderRoute

    routes: dict[str, Any] = {}
    for route_id, provider_model_id, display_name in specs:
        endpoint_id, _, route_slug = route_id.partition(":")
        routes[route_id] = ProviderRoute(
            route_id=route_id,
            endpoint_id=endpoint_id,
            route_slug=route_slug,
            provider_model_id=provider_model_id,
            display_name=display_name,
        )
    return LLMCredentialsFile(provider_routes=routes)


def _fake_roles_env_with_credentials(
    monkeypatch: pytest.MonkeyPatch, credentials: Any
) -> dict[str, Any]:
    from app.models.llm_config import RolesData
    from app.routers import llm
    from app.services import llm_credentials, runtime_activity

    state: dict[str, Any] = {"saved": None, "published": 0, "data": RolesData()}
    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: state["data"])
    monkeypatch.setattr(llm_credentials, "load_credentials", lambda *a, **k: credentials)
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
    monkeypatch.setattr(runtime_activity, "record_runtime_activity", lambda **kwargs: None)
    return state


def test_update_llm_role_accepts_moirai_flat_chain_with_runtime_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact screenshot failure: MoirAI writes back the flat fallback_chain it read
    (route_id + derived runtime_settings, NO canonical_id). It must now SUCCEED, and the
    server must group the two Opus routes under one derived canonical, DeepSeek in its own.
    """
    from app.models.llm_config import RoleEntry

    credentials = _credentials_multi(
        ("anthropic-official:claude-opus-4-8", "claude-opus-4-8", "Claude Opus 4.8"),
        ("openrouter-x:claude-opus-4.8", "anthropic/claude-opus-4.8", None),
        ("deepseek-official:deepseek-v4-pro", "deepseek-v4-pro", None),
    )
    state = _fake_roles_env_with_credentials(monkeypatch, credentials)
    state["data"].roles["analyst"] = RoleEntry()
    deepseek_canonical = credentials.provider_routes[
        "deepseek-official:deepseek-v4-pro"
    ].canonical_id

    result = asyncio.run(
        copilot_tools.update_llm_role_tool.handler(
            {
                "role_name": "analyst",
                "ops": {
                    "set_fallback_chain": [
                        {
                            "route_id": "anthropic-official:claude-opus-4-8",
                            "runtime_settings": {"max_output_tokens": 128000},
                        },
                        {
                            "route_id": "openrouter-x:claude-opus-4.8",
                            "runtime_settings": {"max_output_tokens": 128000},
                        },
                        {
                            "route_id": "deepseek-official:deepseek-v4-pro",
                            "runtime_settings": {"max_output_tokens": 64000},
                        },
                    ]
                },
            }
        )
    )

    assert "is_error" not in result, result
    saved_groups = state["saved"].roles["analyst"].model_groups
    assert [g.canonical_id for g in saved_groups] == [
        "claude-opus-4.8",
        deepseek_canonical,
    ]
    # Two Opus routes collapse into one group, preserving input order.
    assert [pm.route_id for pm in saved_groups[0].provider_models] == [
        "anthropic-official:claude-opus-4-8",
        "openrouter-x:claude-opus-4.8",
    ]
    # display_name derived from the route (falls back to canonical when absent).
    assert saved_groups[0].display_name == "Claude Opus 4.8"
    assert saved_groups[1].display_name == deepseek_canonical
    assert [pm.route_id for pm in saved_groups[1].provider_models] == [
        "deepseek-official:deepseek-v4-pro"
    ]


def test_update_llm_role_flat_chain_unknown_route_lists_all_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.llm_config import RoleEntry

    credentials = _credentials_multi(
        ("anthropic-official:claude-opus-4-8", "claude-opus-4-8", None),
    )
    state = _fake_roles_env_with_credentials(monkeypatch, credentials)
    state["data"].roles["analyst"] = RoleEntry()

    result = asyncio.run(
        copilot_tools.update_llm_role_tool.handler(
            {
                "role_name": "analyst",
                "ops": {
                    "set_fallback_chain": [
                        "anthropic-official:claude-opus-4-8",
                        "ghost-endpoint:missing-a",
                        {"route_id": "ghost-endpoint:missing-b"},
                    ]
                },
            }
        )
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    # Fail-fast lists EVERY invalid route, not just the first.
    assert "ghost-endpoint:missing-a" in text
    assert "ghost-endpoint:missing-b" in text
    assert state["saved"] is None


def test_create_llm_role_flat_chain_mixed_str_and_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = _credentials_multi(
        ("anthropic-official:claude-opus-4-8", "claude-opus-4-8", None),
        ("openrouter-x:claude-opus-4.8", "anthropic/claude-opus-4.8", None),
    )
    state = _fake_roles_env_with_credentials(monkeypatch, credentials)

    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {
                "name": "writer",
                "fallback_chain": [
                    "anthropic-official:claude-opus-4-8",
                    {"route_id": "openrouter-x:claude-opus-4.8", "runtime_settings": {}},
                ],
            }
        )
    )

    assert "is_error" not in result, result
    groups = state["saved"].roles["writer"].model_groups
    # Same canonical → single group, both routes, input order preserved.
    assert len(groups) == 1
    assert groups[0].canonical_id == "claude-opus-4.8"
    assert [pm.route_id for pm in groups[0].provider_models] == [
        "anthropic-official:claude-opus-4-8",
        "openrouter-x:claude-opus-4.8",
    ]


def test_transform_fallback_chain_round_trip_is_lossless() -> None:
    """A role's get_llm_roles fallback_chain projection, fed straight back, reconstructs
    the same grouping (read→write symmetry invariant)."""
    credentials = _credentials_multi(
        ("anthropic-official:claude-opus-4-8", "claude-opus-4-8", "Claude Opus 4.8"),
        ("openrouter-x:claude-opus-4.8", "anthropic/claude-opus-4.8", None),
        ("deepseek-official:deepseek-v4-pro", "deepseek-v4-pro", None),
    )
    projection = [
        {"route_id": "anthropic-official:claude-opus-4-8", "runtime_settings": {"max_output_tokens": 128000}},
        {"route_id": "openrouter-x:claude-opus-4.8", "runtime_settings": {"max_output_tokens": 128000}},
        {"route_id": "deepseek-official:deepseek-v4-pro", "runtime_settings": {}},
    ]

    groups = copilot_tools._transform_fallback_chain_to_model_groups(projection, credentials)

    flattened = [pm.route_id for g in groups for pm in g.provider_models]
    assert flattened == [item["route_id"] for item in projection]


def test_role_write_tools_expose_no_credential_or_endpoint_surface() -> None:
    # R10.3: no credential/endpoint write path through the tool schemas
    for t in (copilot_tools.create_llm_role_tool, copilot_tools.update_llm_role_tool):
        schema_text = str(getattr(t, "input_schema", {}))
        assert "credential" not in schema_text
        assert "api_key" not in schema_text
        assert "endpoint" not in schema_text
