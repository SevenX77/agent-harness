from __future__ import annotations

from app.core.exceptions import STANDARD_ERROR_MAP, standard_http_exception


def test_standard_error_codes_map_to_http_exceptions() -> None:
    expected = {
        "SKILL_NOT_FOUND": 404,
        "SKILL_ALREADY_EXISTS": 409,
        "MANIFEST_VALIDATION_FAILED": 422,
        "COMPILE_FAILED": 200,
        "RUN_SPAWN_FAILED": 500,
        "TERMINAL_SPAWN_FAILED": 500,
        "TERMINAL_LIMIT_REACHED": 503,
        "WEBSOCKET_DISCONNECTED": 499,
        "LLM_FALLBACK_EXHAUSTED": 502,
        "RESUME_CHECKPOINT_NOT_FOUND": 404,
    }

    assert set(STANDARD_ERROR_MAP) == set(expected)
    for error_code, http_status in expected.items():
        exc = standard_http_exception(error_code, "message")
        assert exc.status_code == http_status
        assert exc.detail["error_code"] == error_code
        assert exc.detail["http_status"] == http_status
