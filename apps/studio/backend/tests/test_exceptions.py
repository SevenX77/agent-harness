from __future__ import annotations

import pytest
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
        "LLM_CREDENTIALS_SCHEMA": 422,
        "RESUME_CHECKPOINT_NOT_FOUND": 404,
        "RESUME_VALIDITY_FAILED": 422,
        "TEST_INPUT_NOT_FOUND": 404,
        "TEST_INPUT_ALREADY_EXISTS": 409,
        "TEST_INPUT_VALIDATION_FAILED": 422,
        "SUBGRAPH_PATH_INVALID": 422,
        "SUBGRAPH_PATH_NOT_FOUND": 404,
        "RUN_REQUIRES_PREDICT": 409,
        "RUN_NOT_RUNNING": 409,
    }

    assert set(STANDARD_ERROR_MAP) == set(expected)
    for error_code, http_status in expected.items():
        exc = standard_http_exception(error_code, "message")
        assert exc.status_code == http_status
        assert exc.detail["error_code"] == error_code
        assert exc.detail["http_status"] == http_status


def test_resume_validity_failed_is_not_retryable() -> None:
    assert STANDARD_ERROR_MAP["RESUME_VALIDITY_FAILED"].retry_strategy == "not_retryable"


def test_unregistered_error_code_fails_loudly_instead_of_slipping_through() -> None:
    """An unregistered code must raise at construction, never produce a malformed response."""
    with pytest.raises(KeyError):
        standard_http_exception("DEFINITELY_NOT_REGISTERED", "message")
