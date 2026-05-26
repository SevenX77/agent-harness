from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core import config
from app.models.llm_config import LLMCredentialsFile, RolesData
from app.services.llm_credentials import save_credentials
from app.services.llm_roles import save_roles_file
from fastapi.testclient import TestClient
from graph_agent_gateway.registry.schema import CapabilityValue, ProviderEndpoint, ProviderRoute


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


def test_put_role_v3_skips_needs_setup_and_off_provider_models(
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
        "missing-key-provider:gpt-5": "needs_setup",
        "disabled-provider:gpt-5": "off",
    }


def test_put_role_v3_ready_first_orders_ready_before_untested(
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
        "ready-provider:gpt-5",
        "untested-provider:gpt-5",
    ]


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


def test_put_role_v3_reports_token_downgrade_resolved_settings_and_warning(
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
                "target_output_tokens": {
                    "mode": "target",
                    "value": 128000,
                    "downgrade": "allow_with_warning",
                },
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
    assert report["entries"][0]["route_id"] == "deepseek-official:deepseek-v4-pro"
    assert report["entries"][0]["resolved_settings"]["max_output_tokens"] == 65536
    assert report["entries"][0]["role_fit"] == "downgraded"
    assert report["warnings"][0]["code"] == "token_downgraded"


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


def test_put_role_v3_thinking_preferred_unknown_enters_chain_with_warning(
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
                "thinking": "preferred",
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
    assert entry["role_fit"] == "downgraded"
    assert entry["warnings"][0]["code"] == "thinking_not_enabled"


def test_put_role_v3_thinking_required_unknown_blocks_with_needs_test(
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
                "thinking": "required",
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
    assert body["fallback_chain"] == []
    entry = body["materialization_report"]["entries"][0]
    assert entry["route_id"] == route_id
    assert entry["role_fit"] == "needs_test"
    assert entry["warnings"][0]["code"] == "thinking_capability_unknown"


def test_put_role_v3_returns_fresh_report_without_persisting_report(
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
    roles_path = tmp_path / "settings" / "llm" / "llm_roles.yaml"

    put_response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": "required",
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
    assert put_response.json()["materialization_report"]["entries"][0]["role_fit"] == (
        "needs_test"
    )
    assert "materialization_report" not in roles_path.read_text(encoding="utf-8")

    get_response = client.get("/api/llm/roles/analyst")

    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["materialization_report"]["entries"][0]["role_fit"] == "needs_test"
    assert get_body["materialization_report"]["entries"][0]["route_id"] == route_id


def test_get_role_v3_rematerializes_report_from_current_route_capabilities(
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

    put_response = client.put(
        "/api/llm/roles/analyst",
        json={
            "role_kind": "graph_agent",
            "system_prompt_prefix": "",
            "model_fallback_enabled": True,
            "intent": {
                "provider_preference": "manual_order",
                "thinking": "required",
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
    assert put_response.json()["fallback_chain"] == []

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
    assert get_body["materialization_report"]["entries"][0]["role_fit"] == "using"
    assert get_body["materialization_report"]["entries"][0]["warnings"] == []


def test_put_role_v3_thinking_required_unsupported_blocks_with_not_fit(
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
                "thinking": "required",
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
    assert body["fallback_chain"] == []
    entry = body["materialization_report"]["entries"][0]
    assert entry["route_id"] == route_id
    assert entry["role_fit"] == "not_fit"
    assert entry["warnings"][0]["code"] == "thinking_unsupported"
