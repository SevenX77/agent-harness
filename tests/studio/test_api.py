from __future__ import annotations

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_openapi_registers_phase0_rest_surface(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    expected_paths = {
        "/api/skills",
        "/api/skills/{skill_id}",
        "/api/skills/{skill_id}/lint",
        "/api/skills/{skill_id}/runs",
        "/api/skills/{skill_id}/runs/{run_id}",
        "/api/skills/{skill_id}/runs/{run_id}/resume",
        "/api/skills/{skill_id}/terminal",
        "/api/skills/{skill_id}/test_inputs",
        "/api/skills/{skill_id}/test_inputs/{input_id}",
        "/api/skills/{skill_id}/golden",
        "/api/skills/{skill_id}/golden/{golden_id}",
        "/api/skills/{skill_id}/runs/{run_id}/compare",
        "/api/skills/{skill_id}/copilot/dispatch",
        "/api/skills/{skill_id}/runs/{run_id}/audit",
    }

    assert expected_paths <= set(schema["paths"])
    assert "/api/_debug/value-error" not in schema["paths"]


def test_mvp1_placeholder_endpoints_return_typed_success(client: TestClient) -> None:
    skills_response = client.get("/api/skills")
    assert skills_response.status_code == 200
    assert skills_response.json()[0]["id"] == "phase0-placeholder"

    detail_response = client.get("/api/skills/demo")
    assert detail_response.status_code == 200
    assert detail_response.json()["manifest"]["type"] == "agent"

    run_response = client.post("/api/skills/demo/runs", json={})
    assert run_response.status_code == 202
    assert run_response.json()["status"] == "running"


def test_request_validation_errors_use_error_response(client: TestClient) -> None:
    response = client.post("/api/skills/demo/runs", json={"unexpected": "field"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "MANIFEST_VALIDATION_FAILED"
    assert body["http_status"] == 422
    assert body["retry_strategy"] == "not_retryable"
    assert body["details"]["errors"]


def test_deferred_endpoints_return_structured_501(client: TestClient) -> None:
    response = client.get("/api/skills/demo/golden")

    assert response.status_code == 501
    body = response.json()
    assert body["error_code"] == "NOT_IMPLEMENTED"
    assert body["http_status"] == 501
    assert body["retry_strategy"] == "not_retryable"


def test_value_error_handler_returns_studio_error_response(client: TestClient) -> None:
    response = client.get("/api/_debug/value-error")

    assert response.status_code == 422
    body = response.json()
    assert body == {
        "error_code": "MANIFEST_VALIDATION_FAILED",
        "http_status": 422,
        "message": "Studio debug ValueError",
        "details": None,
        "retry_strategy": "not_retryable",
    }


def test_cors_allows_vite_and_backup_dev_origins(client: TestClient) -> None:
    for origin in ("http://localhost:5173", "http://localhost:3000"):
        response = client.options(
            "/api/skills",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
