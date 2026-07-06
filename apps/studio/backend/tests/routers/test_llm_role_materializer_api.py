from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core import config
from app.models.llm_config import (
    CapabilityValue,
    LLMCredentialsFile,
    ProviderEndpoint,
    ProviderRoute,
    RolesData,
)
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import VerifiedProfile


def _provider_endpoint(
    endpoint_id: str,
    *,
    api_key: str | None = "secret",
    status: str = "verified",
) -> ProviderEndpoint:
    return ProviderEndpoint(
        endpoint_id=endpoint_id,
        display_name=endpoint_id.replace("-", " ").title(),
        protocol="openai_compatible",
        base_url=f"https://{endpoint_id}.example/v1",
        api_key=api_key,
        status=status,
    )


def _provider_route(
    route_id: str,
    *,
    canonical_id: str = "gpt-5",
    status: str = "verified",
) -> ProviderRoute:
    endpoint_id, route_slug = route_id.split(":", 1)
    return ProviderRoute(
        route_id=route_id,
        endpoint_id=endpoint_id,
        route_slug=route_slug,
        provider_model_id=route_slug,
        canonical_id=canonical_id,
        display_name=canonical_id.upper(),
        status=status,
    )


def _seed_materializer_registry(
    tmp_path: Path,
    monkeypatch,
    credentials: LLMCredentialsFile,
) -> None:
    settings_dir = tmp_path / "settings"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", settings_dir)
    active_credentials_path = settings_dir / "llm" / "llm_credentials.json"
    roles_path = settings_dir / "llm" / "llm_roles.yaml"
    save_credentials(credentials, active_credentials_path)
    save_roles_file(roles_path, RolesData(), known_route_ids=set(credentials.provider_routes))


def _open_materializer_route_circuit(
    *,
    route_id: str,
    retry_at: datetime,
    reason_code: str = "rate_limited",
    message: str = "provider is cooling down",
) -> None:
    from app.services.llm_health_store import RuntimeCircuit, SqliteLlmHealthStore

    store = SqliteLlmHealthStore(Path(config.APP_SETTINGS_DIR) / "llm" / "llm_health.sqlite")
    store.open_circuit(
        RuntimeCircuit(
            scope="route",
            scope_id=route_id,
            opened_at=retry_at - timedelta(seconds=60),
            retry_at=retry_at,
            ttl_seconds=60,
            reason_code=reason_code,
            failure_count=1,
            message=message,
        )
    )


def test_put_role_v3_skips_failed_and_off_provider_models(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "ready-provider": _provider_endpoint("ready-provider"),
            "missing-key-provider": _provider_endpoint("missing-key-provider", api_key=None),
            "disabled-provider": _provider_endpoint("disabled-provider", status="disabled"),
        },
        provider_routes={
            "ready-provider:gpt-5": _provider_route("ready-provider:gpt-5"),
            "missing-key-provider:gpt-5": _provider_route("missing-key-provider:gpt-5"),
            "disabled-provider:gpt-5": _provider_route("disabled-provider:gpt-5"),
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [
                        {"route_id": "missing-key-provider:gpt-5"},
                        {"route_id": "disabled-provider:gpt-5"},
                        {"route_id": "ready-provider:gpt-5"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert [entry["route_id"] for entry in response.json()["fallback_chain"]] == [
        "ready-provider:gpt-5"
    ]
    skipped = {
        item["route_id"]: item["ui_state"]
        for item in response.json()["materialization_report"]["skipped_provider_details"]
    }
    assert skipped == {
        "missing-key-provider:gpt-5": "failed",
        "disabled-provider:gpt-5": "off",
    }


def test_put_role_v3_legacy_ready_first_migrates_to_manual_order_without_reordering(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "untested-provider": _provider_endpoint(
                "untested-provider",
                status="unverified_manual",
            ),
            "ready-provider": _provider_endpoint("ready-provider", status="verified"),
        },
        provider_routes={
            "untested-provider:gpt-5": _provider_route(
                "untested-provider:gpt-5",
                status="unverified_manual",
            ),
            "ready-provider:gpt-5": _provider_route("ready-provider:gpt-5", status="verified"),
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "ready_first"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [
                        {"route_id": "untested-provider:gpt-5"},
                        {"route_id": "ready-provider:gpt-5"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert [entry["route_id"] for entry in response.json()["fallback_chain"]] == [
        "untested-provider:gpt-5",
        "ready-provider:gpt-5",
    ]
    assert response.json()["intent"]["provider_preference"] == "manual_order"


def test_put_role_v3_manual_order_preserves_user_provider_order(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "untested-provider": _provider_endpoint(
                "untested-provider",
                status="unverified_manual",
            ),
            "ready-provider": _provider_endpoint("ready-provider", status="verified"),
        },
        provider_routes={
            "untested-provider:gpt-5": _provider_route(
                "untested-provider:gpt-5",
                status="unverified_manual",
            ),
            "ready-provider:gpt-5": _provider_route("ready-provider:gpt-5", status="verified"),
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [
                        {"route_id": "untested-provider:gpt-5"},
                        {"route_id": "ready-provider:gpt-5"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert [entry["route_id"] for entry in response.json()["fallback_chain"]] == [
        "untested-provider:gpt-5",
        "ready-provider:gpt-5",
    ]


def test_put_role_v3_clamps_output_tokens_above_route_max_without_downgrade(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={"deepseek-official": _provider_endpoint("deepseek-official")},
        provider_routes={
            "deepseek-official:deepseek-v4-pro": _provider_route(
                "deepseek-official:deepseek-v4-pro",
                canonical_id="deepseek-v4-pro",
            ).model_copy(
                update={
                    "capabilities": {
                        "max_output_tokens": CapabilityValue(
                            value={
                                "supported": True,
                                "min": 1,
                                "max": 65536,
                                "default": 4096,
                            },
                            source="provider_doc",
                        )
                    }
                }
            )
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "max_output_tokens": 128000,
            },
            "model_groups": [
                {
                    "canonical_id": "deepseek-v4-pro",
                    "display_name": "DeepSeek V4 Pro",
                    "provider_models": [
                        {"route_id": "deepseek-official:deepseek-v4-pro"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    report = response.json()["materialization_report"]
    # Clamped to route max, still "using" — never not_fit / downgraded for tokens.
    assert report["entries"][0]["route_id"] == "deepseek-official:deepseek-v4-pro"
    assert report["entries"][0]["resolved_settings"]["max_output_tokens"] == 65536
    assert report["entries"][0]["role_fit"] == "using"
    assert report["warnings"] == []


def test_put_role_v3_clamps_output_tokens_below_route_min_without_downgrade(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={"deepseek-official": _provider_endpoint("deepseek-official")},
        provider_routes={
            "deepseek-official:deepseek-v4-pro": _provider_route(
                "deepseek-official:deepseek-v4-pro",
                canonical_id="deepseek-v4-pro",
            ).model_copy(
                update={
                    "capabilities": {
                        "max_output_tokens": CapabilityValue(
                            value={
                                "supported": True,
                                "min": 256,
                                "max": 65536,
                                "default": 4096,
                            },
                            source="provider_doc",
                        )
                    }
                }
            )
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "max_output_tokens": 8,
            },
            "model_groups": [
                {
                    "canonical_id": "deepseek-v4-pro",
                    "display_name": "DeepSeek V4 Pro",
                    "provider_models": [
                        {"route_id": "deepseek-official:deepseek-v4-pro"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    report = body["materialization_report"]
    assert report["entries"][0]["resolved_settings"]["max_output_tokens"] == 256
    assert report["entries"][0]["role_fit"] == "using"
    assert body["fallback_chain"][0]["runtime_settings"]["max_output_tokens"] == 256


def test_put_role_v3_temperature_written_to_resolved_settings(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={route_id: _provider_route(route_id)},
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "temperature": 0.2,
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fallback_chain"][0]["runtime_settings"]["temperature"] == 0.2
    assert body["materialization_report"]["entries"][0]["role_fit"] == "using"


def test_put_role_v3_uses_each_route_max_when_output_tokens_unset(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    credentials = LLMCredentialsFile(
        provider_endpoints={
            "fast-provider": _provider_endpoint("fast-provider"),
            "large-provider": _provider_endpoint("large-provider"),
        },
        provider_routes={
            "fast-provider:deepseek-v4-pro": _provider_route(
                "fast-provider:deepseek-v4-pro",
                canonical_id="deepseek-v4-pro",
            ).model_copy(
                update={
                    "capabilities": {
                        "max_output_tokens": CapabilityValue(
                            value={"supported": True, "min": 1, "max": 32768, "default": 4096},
                            source="provider_doc",
                        )
                    }
                }
            ),
            "large-provider:deepseek-v4-pro": _provider_route(
                "large-provider:deepseek-v4-pro",
                canonical_id="deepseek-v4-pro",
            ).model_copy(
                update={
                    "capabilities": {
                        "max_output_tokens": CapabilityValue(
                            value={"supported": True, "min": 1, "max": 131072, "default": 4096},
                            source="provider_doc",
                        )
                    }
                }
            ),
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "max_output_tokens": None,
            },
            "model_groups": [
                {
                    "canonical_id": "deepseek-v4-pro",
                    "display_name": "DeepSeek V4 Pro",
                    "provider_models": [
                        {"route_id": "fast-provider:deepseek-v4-pro"},
                        {"route_id": "large-provider:deepseek-v4-pro"},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    fallback_settings = {
        entry["route_id"]: entry["runtime_settings"]["max_output_tokens"]
        for entry in response.json()["fallback_chain"]
    }
    assert fallback_settings == {
        "fast-provider:deepseek-v4-pro": 32768,
        "large-provider:deepseek-v4-pro": 131072,
    }


def test_delete_role_v3_removes_persisted_role_instead_of_put_merge_retaining_it(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={route_id: _provider_route(route_id)},
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    for role_name in ("analyst", "planner"):
        response = client.put(
            f"/api/llm/roles/{role_name}",
            json={
                "role_kind": "graph_agent",
                "system_prompt_prefix": "",
                "model_fallback_enabled": True,
                "intent": {"provider_preference": "manual_order"},
                "model_groups": [
                    {
                        "canonical_id": "gpt-5",
                        "display_name": "GPT-5",
                        "provider_models": [{"route_id": route_id}],
                    }
                ],
            },
        )
        assert response.status_code == 200

    delete_response = client.delete("/api/llm/roles/analyst")

    assert delete_response.status_code == 200
    delete_roles = delete_response.json()["roles_data"]["roles"]
    assert "analyst" not in delete_roles
    assert "planner" in delete_roles
    get_response = client.get("/api/llm/roles")
    get_roles = get_response.json()["roles_data"]["roles"]
    assert "analyst" not in get_roles
    assert "planner" in get_roles


def test_put_role_v3_keeps_selected_cooling_down_provider_with_warning(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={route_id: _provider_route(route_id)},
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)
    retry_at = datetime.now(UTC) + timedelta(seconds=60)
    _open_materializer_route_circuit(
        route_id=route_id,
        retry_at=retry_at,
        reason_code="rate_limited",
        message="provider returned 429",
    )

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {"provider_preference": "manual_order"},
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [entry["route_id"] for entry in body["fallback_chain"]] == [route_id]
    warning = body["materialization_report"]["warnings"][0]
    assert warning["code"] == "cooling_down"
    assert warning["route_id"] == route_id
    assert warning["retry_at"] == retry_at.isoformat()


def test_put_role_v3_thinking_on_unknown_capability_warns_but_still_fits(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # No thinking_protocol capability on the route → unknown. Best-effort: warn,
    # do not enable reasoning, but keep the route in the chain as "using".
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={route_id: _provider_route(route_id)},
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": True,
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [entry["route_id"] for entry in body["fallback_chain"]] == [route_id]
    entry = body["materialization_report"]["entries"][0]
    assert entry["role_fit"] == "using"
    assert entry["warnings"][0]["code"] == "thinking_unsupported"
    assert body["fallback_chain"][0]["runtime_settings"]["reasoning"]["enabled"] is None


def test_put_role_v3_thinking_on_uses_ready_verified_profile(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={
            route_id: _provider_route(route_id).model_copy(
                update={
                    "verified_profiles": [
                        VerifiedProfile(
                            profile_id="thinking:anthropic_messages:manual",
                            capability="thinking",
                            method_id="anthropic_messages",
                            request_mapper_id="anthropic_thinking_manual_budget",
                            status="ready",
                            default=True,
                            fallback_rank=1,
                            runtime_overrides={
                                "max_output_tokens": 1025,
                                "reasoning": {
                                    "enabled": True,
                                    "budget_tokens": 1024,
                                },
                            },
                        )
                    ],
                }
            )
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": True,
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [entry["route_id"] for entry in body["fallback_chain"]] == [route_id]
    assert body["fallback_chain"][0]["runtime_settings"]["reasoning"]["enabled"] is True
    entry = body["materialization_report"]["entries"][0]
    assert entry["route_id"] == route_id
    assert entry["role_fit"] == "using"
    assert entry["warnings"] == []


def test_get_role_v3_rematerializes_report_from_current_route_capabilities(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    # thinking:true on an unsupported route → warning, no reasoning enabled;
    # after the route's thinking capability flips to true, GET re-materializes
    # and now enables reasoning (report is derived, never persisted).
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={
            route_id: _provider_route(route_id).model_copy(
                update={
                    "capabilities": {
                        "thinking_protocol": CapabilityValue(
                            value=False,
                            source="provider_doc",
                        )
                    }
                }
            )
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)
    roles_path = tmp_path / "settings" / "llm" / "llm_roles.yaml"

    put_response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": True,
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )
    assert put_response.status_code == 200
    put_entry = put_response.json()["materialization_report"]["entries"][0]
    assert put_entry["role_fit"] == "using"
    assert put_entry["warnings"][0]["code"] == "thinking_unsupported"
    # The derived report is never written to the roles file.
    assert "materialization_report" not in roles_path.read_text(encoding="utf-8")

    refreshed_credentials = credentials.model_copy(
        update={
            "provider_routes": {
                route_id: credentials.provider_routes[route_id].model_copy(
                    update={
                        "capabilities": {
                            "thinking_protocol": CapabilityValue(
                                value=True,
                                source="probed_verified",
                            )
                        }
                    }
                )
            }
        }
    )

    save_credentials(
        refreshed_credentials,
        tmp_path / "settings" / "llm" / "llm_credentials.json",
    )

    get_response = client.get("/api/llm/roles/analyst")

    assert get_response.status_code == 200
    get_body = get_response.json()
    assert [entry["route_id"] for entry in get_body["fallback_chain"]] == [route_id]
    assert get_body["fallback_chain"][0]["runtime_settings"]["reasoning"]["enabled"] is True
    assert get_body["materialization_report"]["entries"][0]["role_fit"] == "using"
    assert get_body["materialization_report"]["entries"][0]["warnings"] == []


def test_put_role_v3_thinking_on_unsupported_warns_but_still_fits(
    client: TestClient,
    tmp_path: Path,
    monkeypatch,
) -> None:
    route_id = "ready-provider:gpt-5"
    credentials = LLMCredentialsFile(
        provider_endpoints={"ready-provider": _provider_endpoint("ready-provider")},
        provider_routes={
            route_id: _provider_route(route_id).model_copy(
                update={
                    "capabilities": {
                        "thinking_protocol": CapabilityValue(
                            value=False,
                            source="provider_doc",
                        )
                    }
                }
            )
        },
    )
    _seed_materializer_registry(tmp_path, monkeypatch, credentials)

    response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": True,
            },
            "model_groups": [
                {
                    "canonical_id": "gpt-5",
                    "display_name": "GPT-5",
                    "provider_models": [{"route_id": route_id}],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    # Best-effort: unsupported thinking is a warning, route still in the chain.
    assert [entry["route_id"] for entry in body["fallback_chain"]] == [route_id]
    entry = body["materialization_report"]["entries"][0]
    assert entry["route_id"] == route_id
    assert entry["role_fit"] == "using"
    assert entry["warnings"][0]["code"] == "thinking_unsupported"
    assert body["fallback_chain"][0]["runtime_settings"]["reasoning"]["enabled"] is None
