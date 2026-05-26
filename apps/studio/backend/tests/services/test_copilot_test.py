from __future__ import annotations

import httpx

from app.services.copilot_test import _extract_vendor_error_code


def test_extract_vendor_error_code_prefers_specific_openai_code() -> None:
    response = httpx.Response(
        401,
        json={
            "error": {
                "type": "invalid_request_error",
                "code": "invalid_api_key",
                "message": "Incorrect API key provided.",
            }
        },
    )

    assert _extract_vendor_error_code(response, default="unauthorized") == "invalid_api_key"
